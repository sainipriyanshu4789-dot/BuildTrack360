document.addEventListener('DOMContentLoaded', () => {
  // Level 3 Task 1: clicking a thumbnail opens the enlarged image in a modal
  const modalEl = document.getElementById('imgModal');
  if (modalEl) {
    const modalImg = document.getElementById('modalImg');
    const modal = new bootstrap.Modal(modalEl);
    document.querySelectorAll('.thumb').forEach(thumb => {
      thumb.addEventListener('click', () => {
        modalImg.src = thumb.dataset.full;
        modal.show();
      });
    });
  }

  // Level 3 Task 1: slideshow that changes the image every 3 seconds
  const slides = document.querySelectorAll('#slideshow .slide');
  if (slides.length > 1) {
    let current = 0;
    setInterval(() => {
      slides[current].classList.remove('active');
      current = (current + 1) % slides.length;
      slides[current].classList.add('active');
    }, 3000);
  }
});

// Dummy call button on the Workers page (real calling will be added later)
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.call-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      alert('Calling ' + btn.dataset.name + ' is not active yet. In a future version, one-click calling will be added here.');
    });
  });
});