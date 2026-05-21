#!/usr/bin/env python3
"""Generate a 1/cos(theta) graph for the Camera Angle Matters slide."""

import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(8, 5))
fig.patch.set_facecolor('#fafafa')
ax.set_facecolor('#ffffff')

theta_deg = np.linspace(0, 80, 200)
theta_rad = np.deg2rad(theta_deg)
y = 1 / np.cos(theta_rad)

ax.plot(theta_deg, y, 'b-', linewidth=2.5, label=r'$\frac{1}{\cos(\theta)}$')
ax.axvline(x=0, color='green', linestyle='--', alpha=0.7, label='Normal to plane (θ = 0°)')
ax.axhline(y=1, color='green', linestyle='--', alpha=0.7)

# Highlight points
ax.plot(0, 1, 'go', markersize=10, zorder=5)
ax.plot(30, 1/np.cos(np.deg2rad(30)), 'ro', markersize=8, zorder=5)
ax.plot(60, 1/np.cos(np.deg2rad(60)), 'ro', markersize=8, zorder=5)

ax.annotate('θ = 0°\n1/cos(0) = 1', xy=(0, 1), xytext=(15, 1.3),
            fontsize=11, color='green', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color='green'))
ax.annotate(f'θ = 60°\n1/cos(60°) = {1/np.cos(np.deg2rad(60)):.1f}', xy=(60, 1/np.cos(np.deg2rad(60))), xytext=(50, 3.5),
            fontsize=11, color='red', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color='red'))

ax.set_xlabel('Tilt Angle θ (degrees)', fontsize=12)
ax.set_ylabel('Error Amplification Factor 1/cos(θ)', fontsize=12)
ax.set_title('Error Amplification vs Camera Tilt Angle', fontsize=14, fontweight='bold')
ax.set_xlim(0, 80)
ax.set_ylim(0.8, 6.5)
ax.grid(True, alpha=0.3)
ax.legend(loc='upper left', fontsize=11)

plt.tight_layout()
plt.savefig('media/angle_error_graph.svg', format='svg', facecolor=fig.get_facecolor(), edgecolor='none')
print("Generated media/angle_error_graph.svg")
