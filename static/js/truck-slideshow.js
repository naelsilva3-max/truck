(function () {
  var AUTOPLAY_MS = 5000;

  function initSlideshow(container) {
    var slides = container.querySelectorAll('.truck-slide');
    var dots = container.querySelectorAll('.truck-slide-dot');
    var current = 0;
    var timer = null;

    function show(index) {
      if (!slides.length) return;
      if (index < 0) index = slides.length - 1;
      if (index >= slides.length) index = 0;
      slides[current].classList.remove('active');
      if (dots[current]) dots[current].classList.remove('active');
      current = index;
      slides[current].classList.add('active');
      if (dots[current]) dots[current].classList.add('active');
    }

    function stopAutoplay() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    }

    function startAutoplay() {
      if (slides.length < 2) return;
      stopAutoplay();
      timer = setInterval(function () { show(current + 1); }, AUTOPLAY_MS);
    }

    container.addEventListener('mouseenter', stopAutoplay);
    container.addEventListener('mouseleave', startAutoplay);

    container.truckSlideshowMove = function (delta) {
      stopAutoplay();
      show(current + delta);
      startAutoplay();
    };
    container.truckSlideshowGoTo = function (index) {
      stopAutoplay();
      show(index);
      startAutoplay();
    };

    startAutoplay();
  }

  document.querySelectorAll('.truck-slideshow').forEach(initSlideshow);

  // The onclick="" handlers in the template call these globals directly —
  // there's only ever one slideshow per truck detail page.
  window.truckSlideshowMove = function (delta) {
    var container = document.querySelector('.truck-slideshow');
    if (container && container.truckSlideshowMove) container.truckSlideshowMove(delta);
  };
  window.truckSlideshowGoTo = function (index) {
    var container = document.querySelector('.truck-slideshow');
    if (container && container.truckSlideshowGoTo) container.truckSlideshowGoTo(index);
  };
})();
