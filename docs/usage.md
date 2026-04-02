# Basic usage

This page covers the most common workflows: parsing Org text, loading and
writing files, and turning a `Document` back into text.

## Parse Org text from a string

Use `loads(...)` when you already have the Org source in memory.

```python
>>> from org_parser import loads

>>> document = loads("""
... #+TITLE: Example
... * TODO Write docs
...   SCHEDULED: <2026-04-01 Wed>
... """)

>>> document.title
RichText('Example')
>>> document.children[0].todo
'TODO'
>>> document.children[0].title_text
'Write docs'
```

## Load Org text from a file

Use `load(...)` to parse directly from a `.org` file path.

```python
>>> from pathlib import Path
>>> from org_parser import load

>>> source_path = Path("notes.org")
>>> _ = source_path.write_text("* TODO Inbox\n", encoding="utf-8")

>>> document = load(str(source_path))
>>> document.filename
'notes.org'
>>> document[0].heading_text
'* TODO Inbox'
```

## Update content and stringify it

`Document` and `Heading` objects are mutable. After edits, render back to Org
with `document.render()` or `dumps(document)`.

```python
>>> from org_parser import dumps, loads

>>> document = loads("* TODO Heading\n")
>>> document.children[0].todo = "DONE"
>>> document.children[0].title = "Updated heading"

>>> print(dumps(document))
* DONE Updated heading
```

## `str(document)` vs full document output

- `str(document)` returns only the zeroth section (content before headings).
- `document.render()` and `dumps(document)` return the full document.

```python
>>> from org_parser import dumps, loads

>>> document = loads("#+TITLE: Example\n* TODO Task\n")
>>> str(document)
'#+TITLE: Example\n'
>>> document.render()
'#+TITLE: Example\n* TODO Task\n'
>>> dumps(document) == document.render()
True
```

## Write a document to disk

Use `dump(document, path)` for an explicit output path.

```python
>>> from pathlib import Path
>>> from org_parser import dump, loads

>>> document = loads("* TODO Ship release\n")
>>> output_path = Path("out.org")

>>> dump(document, str(output_path))
>>> output_path.read_text(encoding="utf-8")
'* TODO Ship release\n'
```

You can also assign `document.filename` once and then call `dump(document)`.

```python
>>> from org_parser import dump, loads

>>> document = loads("* TODO Review PR\n")
>>> document.filename = "review.org"
>>> dump(document)
```

If neither `document.filename` nor an explicit path is provided, `dump(...)`
raises `ValueError`.

```python
>>> from org_parser import dump, loads

>>> document = loads("* TODO Missing output path\n")
>>> try:
...     dump(document)
... except ValueError as error:
...     str(error)
'No output filename provided'
```
