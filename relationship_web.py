"""Computes the small radial layout for each entry's "Relationship Web" --
every directly-connected entry (via this entry's own outgoing relationship
dropdowns, or anything linking back to it via a dropdown or [[wiki link]])
arranged in a circle around the current entry. Positions are computed here
in plain Python since Jinja has no trig functions; the result is rendered
as inline SVG directly in entry_detail.html (not a separate image) so each
node can pick up the page's own --cat-* CSS custom properties, same as
every other themed element in the app.
"""

import math

NODE_RADIUS = 16
MAX_NAME_CHARS = 16

# How far out the ring of connected entries sits, in SVG units. Grows with
# node count (up to a cap) so a well-connected entry's labels don't all
# collide into one unreadable clump -- Stormhold, for instance, ended up
# with a dozen-plus Characters pointing their Home City at it.
BASE_RING_RADIUS = 90
RING_RADIUS_CAP = 220
RING_GROWTH_PER_NODE = 6
RING_GROWTH_STARTS_AFTER = 8

# Extra room reserved outside the ring for each node's own circle + label.
LAYOUT_MARGIN = 60


def _truncate(name):
    if len(name) <= MAX_NAME_CHARS:
        return name
    return name[: MAX_NAME_CHARS - 1] + "…"


def build_web(center_entry, connected_entries):
    """Returns None if there's nothing to draw (an isolated entry with no
    relationships at all), otherwise a dict ready for entry_detail.html:
    the overall SVG size, the center node, and every connected node with
    its (x, y) position already computed."""
    n = len(connected_entries)
    if n == 0:
        return None

    ring_radius = min(
        BASE_RING_RADIUS + max(0, n - RING_GROWTH_STARTS_AFTER) * RING_GROWTH_PER_NODE,
        RING_RADIUS_CAP,
    )
    half = ring_radius + NODE_RADIUS + LAYOUT_MARGIN
    size = half * 2

    nodes = []
    for i, e in enumerate(connected_entries):
        # Start at 12 o'clock, go clockwise -- purely cosmetic, but a
        # consistent starting point makes the layout feel less arbitrary
        # from one page load to the next (entry order is otherwise stable
        # anyway, since it comes from a deterministic id-keyed dict).
        angle = (2 * math.pi * i / n) - (math.pi / 2)
        x = half + ring_radius * math.cos(angle)
        y = half + ring_radius * math.sin(angle)
        nodes.append({
            "id": e["id"],
            "display_name": _truncate(e["name"]),
            "full_name": e["name"],
            "category": e["category"],
            "x": round(x, 1),
            "y": round(y, 1),
        })

    return {
        "size": size,
        "center_x": half,
        "center_y": half,
        "center_display_name": _truncate(center_entry["name"]),
        "center_full_name": center_entry["name"],
        "nodes": nodes,
    }
