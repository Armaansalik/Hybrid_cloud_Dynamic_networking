// Chart.js configuration and helper functions for the two live charts.
Chart.defaults.color = '#999';
Chart.defaults.font.family = "'Share Tech Mono', monospace";
Chart.defaults.font.size = 11;

function makeGradient(ctx, colorTop, colorBottom) {
  const g = ctx.createLinearGradient(0, 0, 0, 180);
  g.addColorStop(0, colorTop);
  g.addColorStop(1, colorBottom);
  return g;
}

function buildLiveChart(canvasEl) {
  const ctx = canvasEl.getContext('2d');
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Private A (h2)', data: [], borderColor: '#4caf50',
          backgroundColor: makeGradient(ctx, 'rgba(76,175,80,0.35)', 'rgba(76,175,80,0)'),
          fill: true, tension: 0.35, pointRadius: 0, borderWidth: 2 },
        { label: 'Private B (h3)', data: [], borderColor: '#66bb6a',
          backgroundColor: 'rgba(102,187,106,0)', fill: false, tension: 0.35, pointRadius: 0, borderWidth: 2 },
        { label: 'Cloud (h4)', data: [], borderColor: '#2196f3',
          backgroundColor: makeGradient(ctx, 'rgba(33,150,243,0.35)', 'rgba(33,150,243,0)'),
          fill: true, tension: 0.35, pointRadius: 0, borderWidth: 2 },
        { label: 'Threshold', data: [], borderColor: '#e53935', borderDash: [6,4],
          fill: false, tension: 0, pointRadius: 0, borderWidth: 1.5 },
      ]
    },
    options: {
      animation: { duration: 500, easing: 'easeOutQuart' },
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1c1c2c', borderColor: '#33334f', borderWidth: 1,
          titleColor: '#ffca28', bodyColor: '#eee', padding: 10,
          callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y.toLocaleString()} B/s` }
        }
      },
      scales: {
        x: { grid: { color: '#20202e' }, ticks: { maxTicksLimit: 8 } },
        y: { grid: { color: '#20202e' }, beginAtZero: true,
             ticks: { callback: (v) => v.toLocaleString() } }
      }
    }
  });
}

function updateLiveChart(chart, points, threshold) {
  chart.data.labels = points.map(p => p.time);
  chart.data.datasets[0].data = points.map(p => p.h2);
  chart.data.datasets[1].data = points.map(p => p.h3);
  chart.data.datasets[2].data = points.map(p => p.h4);
  chart.data.datasets[3].data = points.map(() => threshold);
  chart.update('none');
}

function buildLongChart(canvasEl) {
  const ctx = canvasEl.getContext('2d');
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Private A (h2)', data: [], borderColor: '#4caf50', fill:false, tension:0.3, pointRadius:0, borderWidth:2 },
        { label: 'Private B (h3)', data: [], borderColor: '#66bb6a', fill:false, tension:0.3, pointRadius:0, borderWidth:2 },
        { label: 'Cloud (h4)', data: [], borderColor: '#2196f3', fill:false, tension:0.3, pointRadius:0, borderWidth:2 },
      ]
    },
    options: {
      animation: { duration: 400 },
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1c1c2c', borderColor: '#33334f', borderWidth: 1,
          titleColor: '#ffca28', bodyColor: '#eee', padding: 10,
        }
      },
      scales: {
        x: { grid: { color: '#20202e' }, ticks: { maxTicksLimit: 8 } },
        y: { grid: { color: '#20202e' }, beginAtZero: true }
      }
    }
  });
}

function updateLongChart(chart, points) {
  chart.data.labels = points.map(p => p.time);
  chart.data.datasets[0].data = points.map(p => p.h2);
  chart.data.datasets[1].data = points.map(p => p.h3);
  chart.data.datasets[2].data = points.map(p => p.h4);
  chart.update('none');
}
