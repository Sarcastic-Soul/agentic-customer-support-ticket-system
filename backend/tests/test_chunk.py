from app.rag.chunk import chunk_markdown


def test_single_short_section_is_one_chunk():
    md = "# Refund timelines\n\nRefunds take 5-7 business days."
    chunks = chunk_markdown(md)
    assert len(chunks) == 1
    assert chunks[0].heading_path == "Refund timelines"
    assert "Refund timelines" in chunks[0].content
    assert "5-7 business days" in chunks[0].content


def test_nested_headings_build_a_path():
    md = "# Refunds\n\nIntro text.\n\n## Timelines\n\nDetails about timing."
    chunks = chunk_markdown(md)
    paths = [c.heading_path for c in chunks]
    assert "Refunds" in paths
    assert "Refunds > Timelines" in paths


def test_sibling_headings_do_not_nest():
    md = "# A\n\nbody a\n\n# B\n\nbody b"
    chunks = chunk_markdown(md)
    paths = [c.heading_path for c in chunks]
    assert paths == ["A", "B"]


def test_no_headings_returns_single_chunk():
    md = "Just a plain paragraph with no heading at all."
    chunks = chunk_markdown(md)
    assert len(chunks) == 1
    assert chunks[0].heading_path is None


def test_empty_document_returns_no_chunks():
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n  ") == []


def test_long_section_splits_with_overlap():
    body = " ".join(f"word{i}" for i in range(1200))
    md = f"# Long Section\n\n{body}"
    chunks = chunk_markdown(md)
    assert len(chunks) > 1
    # consecutive chunks share some trailing/leading words (the overlap)
    first_words = set(chunks[0].content.split())
    second_words = set(chunks[1].content.split())
    assert first_words & second_words
