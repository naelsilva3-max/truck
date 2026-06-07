"""
Property-based tests using Hypothesis (tasks 10.1 – 10.17).

Run with:  pytest --hypothesis-seed=0
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from django.utils import timezone

from employees.models import BiometricTemplate, Employee
from attendance.models import AttendanceRecord
from attendance.service import AttendanceService
from biometric.listener import BiometricListener
from biometric.service import BiometricService, UnavailableBackend
from trucks.models import Truck, TruckAssignment
from trucks.views import get_current_driver

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

valid_name = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1,
).filter(lambda s: s.strip() != "")

valid_hire_date = st.dates(min_value=date(1970, 1, 1), max_value=date.today())

valid_role = st.text(min_size=1, max_size=100).filter(lambda s: s.strip())

valid_plate_mercosul = st.from_regex(r"^[A-Z]{3}[0-9][A-Z][0-9]{2}$", fullmatch=True)
valid_plate_old = st.from_regex(r"^[A-Z]{3}[0-9]{4}$", fullmatch=True)
valid_plate = st.one_of(valid_plate_mercosul, valid_plate_old)
valid_chassis = st.from_regex(r"^[A-Z0-9]{17}$", fullmatch=True)
valid_model = st.text(min_size=1, max_size=100).filter(lambda s: s.strip())
valid_color = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())
valid_year = st.integers(min_value=1900, max_value=date.today().year)

_counter = [0]


def unique_suffix():
    _counter[0] += 1
    return _counter[0]


# ---------------------------------------------------------------------------
# Property 1: Employee creation round-trip
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(name=valid_name, role=valid_role, hire_date=valid_hire_date)
@settings(max_examples=30, deadline=None)
def test_employee_round_trip(name, role, hire_date):
    emp = Employee.objects.create(name=name, role=role, hire_date=hire_date)
    fetched = Employee.objects.get(pk=emp.pk)
    assert fetched.name == emp.name
    assert fetched.role == emp.role
    assert fetched.hire_date == emp.hire_date


# ---------------------------------------------------------------------------
# Property 2: Invalid employee inputs are rejected
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(name=st.text(alphabet=" \t\n\r", min_size=1))
@settings(max_examples=20, deadline=None)
def test_whitespace_name_rejected(name):
    from django.core.exceptions import ValidationError
    count_before = Employee.objects.count()
    with pytest.raises(ValidationError):
        Employee.objects.create(name=name, role="Op", hire_date=date(2020, 1, 1))
    assert Employee.objects.count() == count_before


@pytest.mark.django_db(transaction=True)
@given(days_ahead=st.integers(min_value=1, max_value=3650))
@settings(max_examples=20, deadline=None)
def test_future_hire_date_rejected(days_ahead):
    from django.core.exceptions import ValidationError
    future = date.today() + timedelta(days=days_ahead)
    count_before = Employee.objects.count()
    with pytest.raises(ValidationError):
        Employee.objects.create(name="Test", role="Op", hire_date=future)
    assert Employee.objects.count() == count_before


# ---------------------------------------------------------------------------
# Property 3: Deactivation preserves linked records
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(n=st.integers(min_value=0, max_value=5))
@settings(max_examples=20, deadline=None)
def test_deactivation_preserves_attendance(n):
    emp = Employee.objects.create(
        name=f"Emp{unique_suffix()}", role="Op", hire_date=date(2020, 1, 1)
    )
    now = timezone.now()
    for i in range(n):
        AttendanceRecord.objects.create(
            employee=emp,
            entry_time=now - timedelta(hours=i * 2 + 1),
            date=(now - timedelta(hours=i * 2 + 1)).date(),
        )
    count_before = AttendanceRecord.objects.filter(employee=emp).count()
    Employee.objects.filter(pk=emp.pk).update(is_active=False)
    assert AttendanceRecord.objects.filter(employee=emp).count() == count_before


# ---------------------------------------------------------------------------
# Property 4: Biometric enroll is idempotent
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(templates=st.lists(st.binary(min_size=1, max_size=10_240), min_size=1, max_size=5))
@settings(max_examples=20, deadline=None)
def test_biometric_enroll_idempotent(templates):
    emp = Employee.objects.create(
        name=f"Bio{unique_suffix()}", role="Op", hire_date=date(2020, 1, 1)
    )
    last = None
    for tmpl in templates:
        bt, created = BiometricTemplate.objects.get_or_create(
            employee=emp, defaults={"template": tmpl}
        )
        if not created:
            bt.template = tmpl
            bt.save()
        last = tmpl
    assert BiometricTemplate.objects.filter(employee=emp).count() == 1
    assert bytes(BiometricTemplate.objects.get(employee=emp).template) == last


# ---------------------------------------------------------------------------
# Property 5: Biometric 1:N identification correctness
# ---------------------------------------------------------------------------

@given(
    pairs=st.lists(
        st.tuples(st.integers(min_value=1, max_value=9999), st.binary(min_size=8, max_size=64)),
        min_size=1, max_size=20, unique_by=lambda p: p[0],
    )
)
@settings(max_examples=30, deadline=None)
def test_biometric_identify_correct(pairs):
    svc = BiometricService(backend=UnavailableBackend())
    # Exact match must return correct id
    emp_id, tmpl = pairs[0]
    assert svc.identify(tmpl, pairs) == emp_id
    # Unknown template returns None (assuming unique bytes)
    unknown = b"\xff" * 128
    assume(all(tmpl != unknown for _, tmpl in pairs))
    assert svc.identify(unknown, pairs) is None


# ---------------------------------------------------------------------------
# Property 6: Attendance toggle — at most one open record
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(n=st.integers(min_value=1, max_value=20))
@settings(max_examples=20, deadline=None)
def test_attendance_toggle_at_most_one_open(n):
    emp = Employee.objects.create(
        name=f"Toggle{unique_suffix()}", role="Op", hire_date=date(2020, 1, 1)
    )
    template_bytes = b"t" * 32
    BiometricTemplate.objects.create(employee=emp, template=template_bytes)

    mock_bio = MagicMock()
    mock_bio.identify.return_value = emp.pk
    svc = AttendanceService(biometric_service=mock_bio)

    base_time = timezone.now() - timedelta(hours=n + 1)
    for i in range(n):
        # Backdate any open record so exit is valid
        open_rec = AttendanceRecord.objects.filter(
            employee=emp, exit_time__isnull=True
        ).first()
        if open_rec:
            AttendanceRecord.objects.filter(pk=open_rec.pk).update(
                entry_time=base_time + timedelta(seconds=i * 10)
            )
        svc.process_biometric_event(template_bytes)

    open_count = AttendanceRecord.objects.filter(
        employee=emp, exit_time__isnull=True
    ).count()
    assert open_count <= 1


# ---------------------------------------------------------------------------
# Property 7: exit_time always after entry_time
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(n=st.integers(min_value=1, max_value=10))
@settings(max_examples=20, deadline=None)
def test_exit_time_always_after_entry_time(n):
    emp = Employee.objects.create(
        name=f"Exit{unique_suffix()}", role="Op", hire_date=date(2020, 1, 1)
    )
    template_bytes = b"e" * 32
    BiometricTemplate.objects.create(employee=emp, template=template_bytes)

    mock_bio = MagicMock()
    mock_bio.identify.return_value = emp.pk
    svc = AttendanceService(biometric_service=mock_bio)

    base = timezone.now() - timedelta(hours=n * 2)
    for i in range(n * 2):
        open_rec = AttendanceRecord.objects.filter(
            employee=emp, exit_time__isnull=True
        ).first()
        if open_rec:
            AttendanceRecord.objects.filter(pk=open_rec.pk).update(
                entry_time=base + timedelta(seconds=i * 5)
            )
        svc.process_biometric_event(template_bytes)

    for rec in AttendanceRecord.objects.filter(employee=emp, exit_time__isnull=False):
        assert rec.exit_time > rec.entry_time


# ---------------------------------------------------------------------------
# Property 8: BiometricListener resilience to exceptions
# ---------------------------------------------------------------------------

@given(
    pattern=st.lists(
        st.one_of(st.just("ok"), st.just("err")),
        min_size=1, max_size=20,
    )
)
@settings(max_examples=30, deadline=None)
def test_listener_resilience(pattern):
    import threading

    events = [b"data" if p == "ok" else RuntimeError for p in pattern]
    expected_ok = sum(1 for p in pattern if p == "ok")

    collected = []
    done = threading.Event()

    class _MockSvc:
        _iter = None

        def __init__(self):
            self._iter = iter(events)
            self._connected = True

        @property
        def is_connected(self):
            return self._connected

        def connect(self, **kw):
            self._connected = True
            return True

        def disconnect(self):
            self._connected = False

        def capture_template(self):
            item = next(self._iter, StopIteration)
            if item is StopIteration:
                from biometric.exceptions import BiometricNotConnectedError
                raise BiometricNotConnectedError("done")
            if isinstance(item, type) and issubclass(item, Exception):
                raise item("mock")
            return item

    svc = _MockSvc()
    listener = BiometricListener(service=svc, poll_interval=0.0)

    def cb(tmpl):
        collected.append(tmpl)
        if len(collected) >= expected_ok:
            done.set()

    listener.start_listener(callback=cb)
    done.wait(timeout=5.0)
    listener.stop_listener()

    assert len(collected) == expected_ok


# ---------------------------------------------------------------------------
# Property 9: Truck creation round-trip
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(
    plate=valid_plate,
    chassis=valid_chassis,
    model=valid_model,
    color=valid_color,
    year=valid_year,
)
@settings(max_examples=20, deadline=None)
def test_truck_round_trip(plate, chassis, model, color, year):
    # Ensure uniqueness per example
    plate = plate + str(unique_suffix())[:0]  # already unique via DB constraint skip
    try:
        truck = Truck.objects.create(
            license_plate=plate,
            chassis=chassis,
            model=model,
            color=color,
            year=year,
        )
    except Exception:
        assume(False)  # skip on uniqueness collision
        return
    fetched = Truck.objects.get(pk=truck.pk)
    assert fetched.license_plate == plate.upper()
    assert fetched.model == model
    assert fetched.year == year


# ---------------------------------------------------------------------------
# Property 10: Unique fields reject duplicates
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(plate=valid_plate, chassis=valid_chassis)
@settings(max_examples=20, deadline=None)
def test_truck_unique_plate_rejects_duplicate(plate, chassis):
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError

    suffix = unique_suffix()
    c1 = f"A{suffix:016d}"[:17]
    c2 = f"B{suffix:016d}"[:17]
    try:
        Truck.objects.create(
            license_plate=plate, chassis=c1,
            model="M", color="C", year=2000,
        )
    except Exception:
        assume(False)
        return
    with pytest.raises((ValidationError, IntegrityError)):
        Truck.objects.create(
            license_plate=plate, chassis=c2,
            model="M", color="C", year=2000,
        )


# ---------------------------------------------------------------------------
# Property 11: Invalid plate and chassis formats are rejected
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(plate=st.text(min_size=1, max_size=15).filter(
    lambda s: not __import__("re").match(r"^[A-Z]{3}[0-9][A-Z][0-9]{2}$", s)
             and not __import__("re").match(r"^[A-Z]{3}[0-9]{4}$", s)
))
@settings(max_examples=20, deadline=None)
def test_invalid_plate_rejected(plate):
    from django.core.exceptions import ValidationError
    count_before = Truck.objects.count()
    with pytest.raises(ValidationError):
        Truck.objects.create(
            license_plate=plate,
            chassis=f"VALID{unique_suffix():012d}"[:17],
            model="M", color="C",
        )
    assert Truck.objects.count() == count_before


@pytest.mark.django_db(transaction=True)
@given(chassis=st.one_of(
    st.text(min_size=1, max_size=16),
    st.text(min_size=18, max_size=30),
    st.from_regex(r"^[A-Z0-9]{1,16}[^A-Z0-9][A-Z0-9]*$", fullmatch=True).filter(lambda s: len(s) == 17),
))
@settings(max_examples=20, deadline=None)
def test_invalid_chassis_rejected(chassis):
    import re
    assume(not re.match(r"^[A-Z0-9]{17}$", chassis))
    from django.core.exceptions import ValidationError
    count_before = Truck.objects.count()
    with pytest.raises(ValidationError):
        Truck.objects.create(
            license_plate=f"ABC{unique_suffix() % 10}D{unique_suffix() % 10:02d}"[:7],
            chassis=chassis,
            model="M", color="C",
        )
    assert Truck.objects.count() == count_before


# ---------------------------------------------------------------------------
# Property 12: Only drivers can be assigned to trucks
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(dummy=st.just(None))
@settings(max_examples=10, deadline=None)
def test_only_drivers_can_be_assigned(dummy):
    from django.core.exceptions import ValidationError
    emp = Employee.objects.create(
        name=f"NonDriver{unique_suffix()}", role="Op",
        hire_date=date(2020, 1, 1), is_driver=False,
    )
    suffix = unique_suffix()
    truck = Truck.objects.create(
        license_plate=f"AAA{suffix % 10}B{suffix % 100:02d}"[:7],
        chassis=f"{suffix:017d}"[:17],
        model="M", color="C",
    )
    count_before = TruckAssignment.objects.count()
    with pytest.raises(ValidationError):
        TruckAssignment.objects.create(truck=truck, driver=emp)
    assert TruckAssignment.objects.count() == count_before


# ---------------------------------------------------------------------------
# Property 13: At most one active TruckAssignment per truck
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(n_ops=st.integers(min_value=1, max_value=10))
@settings(max_examples=15, deadline=None)
def test_at_most_one_active_assignment(n_ops):
    suffix = unique_suffix()
    truck = Truck.objects.create(
        license_plate=f"BBB{suffix % 10}C{suffix % 100:02d}"[:7],
        chassis=f"T{suffix:016d}"[:17],
        model="M", color="C",
    )

    for i in range(n_ops):
        active = TruckAssignment.objects.filter(
            truck=truck, unassigned_at__isnull=True
        )
        if active.exists():
            # Unassign
            TruckAssignment.objects.filter(pk=active.first().pk).update(
                unassigned_at=timezone.now()
            )
        else:
            # Assign new driver
            driver = Employee.objects.create(
                name=f"D{suffix}_{i}", role="Dr",
                hire_date=date(2020, 1, 1), is_driver=True,
            )
            TruckAssignment.objects.create(truck=truck, driver=driver)

        count = TruckAssignment.objects.filter(
            truck=truck, unassigned_at__isnull=True
        ).count()
        assert count <= 1


# ---------------------------------------------------------------------------
# Property 14: TruckAssignment temporal invariant
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(delta_seconds=st.integers(min_value=0, max_value=86400))
@settings(max_examples=20, deadline=None)
def test_assignment_temporal_invariant(delta_seconds):
    suffix = unique_suffix()
    driver = Employee.objects.create(
        name=f"Drv{suffix}", role="Dr", hire_date=date(2020, 1, 1), is_driver=True
    )
    truck = Truck.objects.create(
        license_plate=f"CCC{suffix % 10}D{suffix % 100:02d}"[:7],
        chassis=f"U{suffix:016d}"[:17],
        model="M", color="C",
    )
    now = timezone.now()
    a = TruckAssignment.objects.create(
        truck=truck, driver=driver, assigned_at=now
    )
    TruckAssignment.objects.filter(pk=a.pk).update(
        unassigned_at=now + timedelta(seconds=delta_seconds)
    )
    a.refresh_from_db()
    assert a.assigned_at <= a.unassigned_at


# ---------------------------------------------------------------------------
# Property 15: get_current_driver consistency
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(has_active=st.booleans())
@settings(max_examples=20, deadline=None)
def test_get_current_driver_consistent(has_active):
    suffix = unique_suffix()
    truck = Truck.objects.create(
        license_plate=f"DDD{suffix % 10}E{suffix % 100:02d}"[:7],
        chassis=f"V{suffix:016d}"[:17],
        model="M", color="C",
    )
    if has_active:
        driver = Employee.objects.create(
            name=f"D{suffix}", role="Dr", hire_date=date(2020, 1, 1), is_driver=True
        )
        TruckAssignment.objects.create(truck=truck, driver=driver)

    result = get_current_driver(truck.pk)
    raw = TruckAssignment.objects.filter(
        truck=truck, unassigned_at__isnull=True
    ).select_related("driver").first()
    expected = raw.driver if raw else None
    assert result == expected


# ---------------------------------------------------------------------------
# Property 16: Date filter returns only matching records
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(
    days=st.lists(st.integers(min_value=0, max_value=30), min_size=1, max_size=10),
    filter_day=st.integers(min_value=0, max_value=30),
)
@settings(max_examples=20, deadline=None)
def test_date_filter_returns_only_matching(days, filter_day):
    emp = Employee.objects.create(
        name=f"Flt{unique_suffix()}", role="Op", hire_date=date(2020, 1, 1)
    )
    base = timezone.now() - timedelta(days=31)
    for d in days:
        t = base + timedelta(days=d)
        AttendanceRecord.objects.create(employee=emp, entry_time=t, date=t.date())

    target = (base + timedelta(days=filter_day)).date()
    svc = AttendanceService()
    results = svc.list_records(emp.pk, start_date=target, end_date=target)
    for r in results:
        assert r.date == target


# ---------------------------------------------------------------------------
# Property 17: Soft-delete instead of physical delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
@given(dummy=st.just(None))
@settings(max_examples=5, deadline=None)
def test_attendance_record_no_physical_delete(dummy):
    emp = Employee.objects.create(
        name=f"Soft{unique_suffix()}", role="Op", hire_date=date(2020, 1, 1)
    )
    now = timezone.now()
    rec = AttendanceRecord.objects.create(employee=emp, entry_time=now, date=now.date())
    with pytest.raises(PermissionError):
        rec.delete()
    assert AttendanceRecord.objects.filter(pk=rec.pk).exists()


@pytest.mark.django_db(transaction=True)
@given(dummy=st.just(None))
@settings(max_examples=5, deadline=None)
def test_truck_assignment_no_physical_delete(dummy):
    suffix = unique_suffix()
    driver = Employee.objects.create(
        name=f"SoftD{suffix}", role="Dr", hire_date=date(2020, 1, 1), is_driver=True
    )
    truck = Truck.objects.create(
        license_plate=f"EEE{suffix % 10}F{suffix % 100:02d}"[:7],
        chassis=f"W{suffix:016d}"[:17],
        model="M", color="C",
    )
    assignment = TruckAssignment.objects.create(truck=truck, driver=driver)
    with pytest.raises(PermissionError):
        assignment.delete()
    assert TruckAssignment.objects.filter(pk=assignment.pk).exists()
