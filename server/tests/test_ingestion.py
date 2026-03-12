from __future__ import annotations

import unittest

from server.app.ingestion import MarkdownLoader, MarkdownParser


class IngestionConfigTests(unittest.TestCase):
    def test_notes_chunking_uses_parser_configuration(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "type: notes",
                "title: Chunk Config Test",
                "---",
                "",
                "# Section",
                "",
                "A" * 90,
                "B" * 90,
                "C" * 90,
                "D" * 90,
                "",
            ]
        )
        loaded = MarkdownLoader().load_text(markdown, source_path="chunk-test.md")

        parsed = MarkdownParser(notes_chunk_size_chars=160, notes_overlap_chars=40).parse(loaded)

        self.assertGreaterEqual(len(parsed.notes_chunks), 2)
        self.assertLessEqual(max(len(chunk.text) for chunk in parsed.notes_chunks), 181)
        self.assertEqual(parsed.notes_chunks[0].heading_path, ["Section"])
        self.assertGreater(parsed.notes_chunks[0].line_range.end, parsed.notes_chunks[0].line_range.start)

