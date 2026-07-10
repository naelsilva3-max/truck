(function () {
  function isPdfFile(file) {
    return file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');
  }

  function setState(box, state, showingPdf) {
    var placeholder = box.querySelector('.camera-placeholder');
    var video = box.querySelector('.camera-video');
    var snapshot = box.querySelector('.camera-snapshot');
    var pdfPreview = box.querySelector('.camera-pdf-preview');
    var startBtn = box.querySelector('.camera-btn-start');
    var fileBtn = box.querySelector('.camera-btn-file');
    var captureBtn = box.querySelector('.camera-btn-capture');
    var retakeBtn = box.querySelector('.camera-btn-retake');

    var showSnapshot = state === 'captured' && !showingPdf;
    var showPdf = state === 'captured' && showingPdf;

    placeholder.style.display = state === 'idle' ? 'flex' : 'none';
    video.style.display = state === 'live' ? 'block' : 'none';
    snapshot.style.display = showSnapshot ? 'block' : 'none';
    if (pdfPreview) pdfPreview.style.display = showPdf ? 'block' : 'none';
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
    var pdfEmbed = box.querySelector('.camera-pdf-embed');
    var pdfOpenLink = box.querySelector('.camera-pdf-open-link');
    var startBtn = box.querySelector('.camera-btn-start');
    var fileBtn = box.querySelector('.camera-btn-file');
    var captureBtn = box.querySelector('.camera-btn-capture');
    var retakeBtn = box.querySelector('.camera-btn-retake');
    var input = box.querySelector('input[type="file"]');
    var facing = box.dataset.facing || 'user';
    var stream = null;
    var currentObjectUrl = null;

    function stopStream() {
      if (stream) {
        stream.getTracks().forEach(function (track) { track.stop(); });
        stream = null;
      }
    }

    function revokeCurrentObjectUrl() {
      if (currentObjectUrl) {
        URL.revokeObjectURL(currentObjectUrl);
        currentObjectUrl = null;
      }
    }

    function showImagePreview(objectUrl) {
      revokeCurrentObjectUrl();
      currentObjectUrl = objectUrl;
      snapshot.src = objectUrl;
      setState(box, 'captured', false);
    }

    // PDFs can't come from the webcam, only from a real file pick -- this
    // is only ever called from the file <input> change handler below.
    function showPdfPreview(objectUrl) {
      revokeCurrentObjectUrl();
      currentObjectUrl = objectUrl;
      if (pdfEmbed) pdfEmbed.setAttribute('src', objectUrl);
      if (pdfOpenLink) pdfOpenLink.setAttribute('href', objectUrl);
      setState(box, 'captured', true);
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
      var objectUrl = URL.createObjectURL(file);
      if (pdfEmbed && isPdfFile(file)) {
        showPdfPreview(objectUrl);
      } else {
        showImagePreview(objectUrl);
      }
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
        stopStream();
        showImagePreview(URL.createObjectURL(blob));
      }, 'image/jpeg', 0.92);
    });

    retakeBtn.addEventListener('click', function () {
      input.value = '';
      revokeCurrentObjectUrl();
      setState(box, 'idle', false);
      clearError(box);
    });

    setState(box, 'idle', false);
  }

  document.querySelectorAll('.camera-capture').forEach(initCameraCapture);
})();
