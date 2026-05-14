/**
 * Quantum Terminal — Particle Field
 *
 * Subtle particle animation on the background canvas.
 * Low-CPU, deep-space feel. Activated on mount, cleaned up on unmount.
 */
import { onMounted, onUnmounted } from "vue";

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
}

export function useParticles() {
  let canvas: HTMLCanvasElement | null = null;
  let ctx: CanvasRenderingContext2D | null = null;
  let particles: Particle[] = [];
  let animId = 0;
  let w = 0;
  let h = 0;

  function resize() {
    canvas = document.getElementById("qt-particles") as HTMLCanvasElement;
    if (!canvas) return;
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = w;
    canvas.height = h;
  }

  function spawn(count: number) {
    particles = Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      size: Math.random() * 1.5 + 0.5,
      alpha: Math.random() * 0.3 + 0.05,
    }));
  }

  function draw() {
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, w, h);

    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;

      // Wrap around edges
      if (p.x < 0) p.x = w;
      if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h;
      if (p.y > h) p.y = 0;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0, 212, 255, ${p.alpha})`;
      ctx.fill();

      // Occasional glow for larger particles
      if (p.size > 1.2) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * 3, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(0, 212, 255, ${p.alpha * 0.15})`;
        ctx.fill();
      }
    }

    // Draw subtle connections between nearby particles
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 100) {
          ctx!.beginPath();
          ctx!.moveTo(particles[i].x, particles[i].y);
          ctx!.lineTo(particles[j].x, particles[j].y);
          ctx!.strokeStyle = `rgba(0, 212, 255, ${0.03 * (1 - dist / 100)})`;
          ctx!.lineWidth = 0.5;
          ctx!.stroke();
        }
      }
    }

    animId = requestAnimationFrame(draw);
  }

  onMounted(() => {
    canvas = document.getElementById("qt-particles") as HTMLCanvasElement;
    if (!canvas) return;
    ctx = canvas.getContext("2d");
    resize();
    spawn(60);
    draw();
    window.addEventListener("resize", () => {
      resize();
      spawn(60);
    });
  });

  onUnmounted(() => {
    cancelAnimationFrame(animId);
    window.removeEventListener("resize", resize);
  });
}
