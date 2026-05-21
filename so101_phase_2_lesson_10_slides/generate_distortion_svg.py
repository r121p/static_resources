#!/usr/bin/env python3
"""Generate an SVG visualizing radial distortion correction using matplotlib."""

import matplotlib.pyplot as plt
import numpy as np

# Figure size (inches) -> SVG output
fig, ax = plt.subplots(figsize=(10, 7.5))
fig.patch.set_facecolor('#fafafa')
ax.set_facecolor('#ffffff')

# Optical center
cx, cy = 0.5, 0.5

# Distortion coefficients (barrel distortion: k1 < 0)
k1 = -0.8
k2 = 0.15


def distort(xu, yu):
    """Apply radial distortion to undistorted normalized coordinates."""
    dx = xu - cx
    dy = yu - cy
    ru2 = dx * dx + dy * dy
    factor = 1.0 + k1 * ru2 + k2 * ru2 * ru2
    xd = cx + dx * factor
    yd = cy + dy * factor
    return xd, yd


# Generate straight line of undistorted points (horizontal, slightly above center)
n_points = 9
x_undist = np.linspace(0.15, 0.85, n_points)
y_undist = np.full_like(x_undist, 0.72)

# Compute distorted points
x_dist = []
y_dist = []
for xu, yu in zip(x_undist, y_undist):
    xd, yd = distort(xu, yu)
    x_dist.append(xd)
    y_dist.append(yd)

x_dist = np.array(x_dist)
y_dist = np.array(y_dist)

# Plot optical center
ax.plot(cx, cy, 'ko', markersize=8, label='Optical Center')
ax.annotate('Optical Center', (cx, cy), textcoords="offset points", xytext=(0, -20),
            ha='center', fontsize=10, color='#333')

# Plot radius lines to distorted points (red dashed)
for xd, yd in zip(x_dist, y_dist):
    ax.plot([cx, xd], [cy, yd], 'r--', alpha=0.4, linewidth=1.2)

# Plot radius lines to undistorted points (green dashed)
for xu, yu in zip(x_undist, y_undist):
    ax.plot([cx, xu], [cy, yu], 'g--', alpha=0.4, linewidth=1.2)

# Plot distorted points and curved path
ax.plot(x_dist, y_dist, 'ro', markersize=10, alpha=0.8, label='Distorted points (curved)')
# Smooth curve through distorted points
t = np.linspace(0, 1, 200)
x_spline = np.interp(t, np.linspace(0, 1, n_points), x_dist)
y_spline = np.interp(t, np.linspace(0, 1, n_points), y_dist)
ax.plot(x_spline, y_spline, 'r--', alpha=0.6, linewidth=2)

# Plot undistorted points and straight line
ax.plot(x_undist, y_undist, 'go', markersize=10, alpha=0.9, label='Corrected points (straight)')
ax.plot([x_undist[0], x_undist[-1]], [y_undist[0], y_undist[-1]], 'g-', alpha=0.8, linewidth=2)

# Add arrow showing correction for one point (middle point)
idx = n_points // 2
ax.annotate('', xy=(x_undist[idx], y_undist[idx]), xytext=(x_dist[idx], y_dist[idx]),
            arrowprops=dict(arrowstyle='->', color='#ff9800', lw=2))

# Label r and r_corr
ax.text(x_dist[2] + 0.02, y_dist[2] - 0.04, 'r', color='red', fontsize=13, fontweight='bold')
ax.text(x_undist[6] + 0.02, y_undist[6] - 0.04, r'$r_{corr} \cdot r$', color='green', fontsize=13, fontweight='bold')

# Set limits and aspect
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.set_aspect('equal')
ax.axis('off')

# Title
ax.set_title('Radial Distortion Correction', fontsize=16, fontweight='bold', pad=15)

# Legend
ax.legend(loc='lower center', fontsize=11, frameon=True, ncol=3,
          bbox_to_anchor=(0.5, -0.02), facecolor='#f5f5f5', edgecolor='#ddd')

# Add equation text at bottom
fig.text(0.5, 0.02, r'$r_{corr} = 1 + k_1 r^2 + k_2 r^4 + \dots$',
         ha='center', fontsize=12, color='#555')

plt.tight_layout(rect=[0, 0.05, 1, 1])
plt.savefig('media/radial_distortion_visual.svg', format='svg', facecolor=fig.get_facecolor(),
            edgecolor='none', bbox_inches='tight')
print("Generated media/radial_distortion_visual.svg")
