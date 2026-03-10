#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


BJJ_FIXTURES = [
    {
        "filename": "bjj_turtle_escape_foundations.md",
        "title": "Turtle Escape Foundations",
        "sections": [
            {
                "date": "2026-03-01",
                "position": "turtle",
                "orientation": "下位",
                "distance": "近距离",
                "goal": "escape",
                "your_action": "tripod post to recover base",
                "opponent_response": "dragged the wrist and collapsed the post",
                "opponent_control": "袖子",
                "your_adjustment": "hide elbow first and turn the forehead inward",
                "notes": "base was stable only after the elbow line recovered",
            },
            {
                "date": "2026-03-04",
                "position": "turtle",
                "orientation": "下位",
                "distance": "近距离",
                "goal": "escape",
                "your_action": "hand-fight before posting",
                "opponent_response": "followed the hips and stayed heavy",
                "opponent_control": "腰带",
                "your_adjustment": "win the inside elbow before the second post",
                "notes": "safer than posting blindly",
            },
        ],
    },
    {
        "filename": "bjj_half_guard_knee_shield.md",
        "title": "Half Guard Knee Shield",
        "sections": [
            {
                "date": "2026-03-06",
                "position": "half guard",
                "orientation": "下位",
                "distance": "中距离",
                "goal": "recover_guard",
                "your_action": "frame the neck and insert knee shield",
                "opponent_response": "cross-faced and flattened the hips",
                "opponent_control": "crossface",
                "your_adjustment": "hide the near elbow and rotate onto the side first",
                "notes": "knee shield only worked after angle recovery",
            }
        ],
    },
    {
        "filename": "bjj_closed_guard_arm_drag.md",
        "title": "Closed Guard Arm Drag",
        "sections": [
            {
                "date": "2026-03-08",
                "position": "closed guard",
                "orientation": "下位",
                "distance": "近距离",
                "goal": "back_take",
                "your_action": "arm drag to climb the back",
                "opponent_response": "postured up before the hip angle changed",
                "opponent_control": "袖子",
                "your_adjustment": "break posture first with a collar pull before dragging",
                "notes": "drag timing improved when knees stayed tight",
            }
        ],
    },
    {
        "filename": "bjj_headquarters_retention.md",
        "title": "Headquarters Retention",
        "sections": [
            {
                "date": "2026-03-10",
                "position": "headquarters",
                "orientation": "下位",
                "distance": "中距离",
                "goal": "guard_retention",
                "your_action": "shin frame and hip escape",
                "opponent_response": "pinned the top knee and walked around the legs",
                "opponent_control": "裤腿",
                "your_adjustment": "stiff-arm the shoulder and recover the outside foot first",
                "notes": "the outside foot recovery created enough space to square up",
            }
        ],
    },
    {
        "filename": "bjj_mount_elbow_knee_escape.md",
        "title": "Mount Elbow Knee Escape",
        "sections": [
            {
                "date": "2026-03-12",
                "position": "mount",
                "orientation": "下位",
                "distance": "近距离",
                "goal": "escape",
                "your_action": "bridge and insert knee elbow frame",
                "opponent_response": "switched to a high mount and floated the hips",
                "opponent_control": "underhook",
                "your_adjustment": "trap the foot before bridging and keep elbows stapled",
                "notes": "foot trap timing decided whether the knee could enter",
            }
        ],
    },
    {
        "filename": "bjj_guard_passing_balance.md",
        "title": "Standing Guard Passing Balance",
        "sections": [
            {
                "date": "2026-03-14",
                "position": "open guard",
                "orientation": "上位",
                "distance": "中距离",
                "goal": "pass",
                "your_action": "stand and split the hooks before knee slicing",
                "opponent_response": "off-balanced the standing leg and re-pummeled hooks",
                "opponent_control": "脚踝",
                "your_adjustment": "win head position and angle the knee line outward first",
                "notes": "balance was much better once head and hips moved together",
            }
        ],
    },
]


NOTES_FIXTURES = [
    {
        "filename": "notes_borges_memory_maze.md",
        "title": "Borges Memory Maze",
        "body": """# Borges and Memory

Memory in Borges is rarely a warehouse. It behaves more like a maze whose rooms are rebuilt while you walk.

## Mirror Motif

The mirror does not merely reflect. It multiplies hesitation and makes certainty theatrical.

## Retrieval Note

Use this note when testing literary retrieval around mirrors, libraries, and recursive memory.
""",
    },
    {
        "filename": "notes_training_patience.md",
        "title": "Training and Patience",
        "body": """# Patience in Training

Progress often hides inside repetitions that feel too small to matter on the day they are done.

## Observation

Technical confidence improves faster when the athlete names one controllable detail after each round.

## Writing Angle

This note is useful for reflective prompts about consistency, craft, and delayed feedback.
""",
    },
    {
        "filename": "notes_city_rain_fragment.md",
        "title": "City Rain Fragment",
        "body": """# City Rain Fragment

The rain made every storefront look briefly more sincere than it was in daylight.

## Sentence Seed

Try contrasting neon light with wet pavement, then pivot into memory instead of description.
""",
    },
    {
        "filename": "notes_library_order.md",
        "title": "Library and Order",
        "body": """# Library and Order

Any catalog is a temporary argument about what should stay near what.

## Fragment

Classification feels objective only until the first difficult book refuses its shelf.

## Query Hook

Useful for questions about libraries, order, disorder, curation, and essay structure.
""",
    },
    {
        "filename": "notes_body_learning.md",
        "title": "Body Learning Notes",
        "body": """# Body Learning

The body understands sequences long before the ego agrees that the sequence is familiar.

## Practice Note

When language lags behind timing, drill names can mislead more than they help.
""",
    },
]


def main() -> None:
    bjj_dir = FIXTURE_ROOT / "bjj"
    notes_dir = FIXTURE_ROOT / "notes"
    bjj_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for fixture in BJJ_FIXTURES:
        path = bjj_dir / fixture["filename"]
        path.write_text(render_bjj_markdown(fixture), encoding="utf-8")
        written.append(path)

    for fixture in NOTES_FIXTURES:
        path = notes_dir / fixture["filename"]
        path.write_text(render_notes_markdown(fixture), encoding="utf-8")
        written.append(path)

    print(f"generated_markdown_fixture_count={len(written)}")
    for path in written:
        print(path.relative_to(FIXTURE_ROOT.parent))


def render_bjj_markdown(fixture: dict) -> str:
    lines = [
        "---",
        "type: BJJ",
        f"title: {fixture['title']}",
        "---",
        "",
    ]
    for section in fixture["sections"]:
        lines.extend(
            [
                f"## {section['date']}",
                f"- position: {section['position']}",
                f"- orientation: {section['orientation']}",
                f"- distance: {section['distance']}",
                f"- goal: {section['goal']}",
                f"- your_action: {section['your_action']}",
                f"- opponent_response: {section['opponent_response']}",
                f"- opponent_control: {section['opponent_control']}",
                f"- your_adjustment: {section['your_adjustment']}",
                f"- notes: {section['notes']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_notes_markdown(fixture: dict) -> str:
    return "\n".join(
        [
            "---",
            "type: notes",
            f"title: {fixture['title']}",
            "---",
            "",
            fixture["body"].rstrip(),
            "",
        ]
    )


if __name__ == "__main__":
    main()
