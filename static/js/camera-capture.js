(function () {
  function setState(box, state) {
    var placeholder = box.querySelector('.camera-placeholder');
    var video = box.querySelector('.camera-video');
    var snapshot = box.querySelector('.camera-snapshot');
    var startBtn = box.querySelector('.camera-btn-start');
    var fileBtn = box.querySelector('.camera-btn-file');
    var captureBtn = box.querySelector('.camera-btn-capture');
    var retakeBtn = box.querySelector('.camera-btn-retake');

    placeholder.style.display = state === 'idle' ? 'flex' : 'none';
    video.style.display = state === 'live' ? 'block' : 'none';
    snapshot.style.display = state === 'captured' ? 'block' : 'none';
    startBtn.style.display = state === 'idle' ? 'inline-flex' : 'none';
    if (fileBtn) fileBtn.style.display = state === 'idle' ? 'inline-flex' : 'none';
    captureBtn.style.display = state === 'live' ? 'inline-flex' : 'none';
    retakeBtn.style.display = state === 'captured' ? 'inline-flex' : 'none';
  }

  function showError(box, message) {
    var errorEl = box.querySelector('.camera-error');
    errorEl.textContent = message;
    errorEl.style.display = 'block';
  }

  function clearError(box) {
    var errorEl = box.querySelector('.camera-error');
    errorEl.textContent = '';
    errorEl.style.display = 'none';
  }

  function initCameraCapture(box) {
    var video = box.querySelector('.camera-video');
    var canvas = box.querySelector('.camera-canvas');
    var snapshot = box.querySelector('.camera-snapshot');
    var startBtn = box.querySelector('.camera-btn-start');
    var fileBtn = box.querySelector('.camera-btn-file');
    var captureBtn = box.querySelector('.camera-btn-capture');
    var retakeBtn = box.querySelector('.camera-btn-retake');
    var input = box.querySelector('input[type="file"]');
    var facing = box.dataset.facing || 'user';
    var stream = null;

    function stopStream() {
      if (stream) {
        stream.getTracks().forEach(function (track) { track.stop(); });
        stream = null;
      }
    }

    startBtn.addEventListener('click', function () {
      clearError(box);
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showError(box, 'Este navegador não suporta captura de câmera.');
        return;
      }
      navigator.mediaDevices.getUserMedia({ video: { facingMode: facing }, audio: false })
        .then(function (mediaStream) {
          stream = mediaStream;
          video.srcObject = mediaStream;
          setState(box, 'live');
        })
        .catch(function () {
          showError(box, 'Não foi possível acessar a câmera. Verifique as permissões do navegador.');
        });
    });

    if (fileBtn) {
      fileBtn.addEventListener('click', function () {
        clearError(box);
        input.click();
      });
    }

    // Fires when a file is chosen via the native picker (camera-btn-file).
    // Programmatically assigning input.files from the capture flow below does
    // not dispatch 'change', so this only ever runs for a real file pick.
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) return;
      stopStream();
      var previousUrl = snapshot.dataset.objectUrl;
      if (previousUrl) URL.revokeObjectURL(previousUrl);
      var objectUrl = URL.createObjectURL(file);
      snapshot.src = objectUrl;
      snapshot.dataset.objectUrl = objectUrl;
      setState(box, 'captured');
    });

    captureBtn.addEventListener('click', function () {
      var width = video.videoWidth;
      var height = video.videoHeight;
      if (!width || !height) return;
      canvas.width = width;
      canvas.height = height;
      canvas.getContext('2d').drawImage(video, 0, 0, width, height);
      canvas.toBlob(function (blob) {
        if (!blob) return;
        var file = new File([blob], 'captura.jpg', { type: 'image/jpeg' });
        var dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        input.files = dataTransfer.files;
        var previousUrl = snapshot.dataset.objectUrl;
        if (previousUrl) URL.revokeObjectURL(previousUrl);
        var objectUrl = URL.createObjectURL(blob);
        snapshot.src = objectUrl;
        snapshot.dataset.objectUrl = objectUrl;
        stopStream();
        setState(box, 'captured');
      }, 'image/jpeg', 0.92);
    });

    retakeBtn.addEventListener('click', function () {
      input.value = '';
      setState(box, 'idle');
      clearError(box);
    });

    setState(box, 'idle');
  }

  document.querySelectorAll('.camera-capture').forEach(initCameraCapture);
})();
