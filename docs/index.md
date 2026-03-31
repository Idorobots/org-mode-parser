# org-parser

`org-parser` provides a semantic Python API for Org documents backed by
tree-sitter.

## Basic usage

Parse Org text into a `Document`:

```python
>>> from org_parser import loads

>>> document = loads("""
... #+TITLE: Example
... * TODO Write docs
...   SCHEDULED: <2026-04-01 Wed>
... """)

>>> document.title
'Example'
>>> document.children[0].todo
'TODO'
```

Traverse headings and update content:

```python
>>> from org_parser import dumps, loads

>>> document = loads("* Heading\n")
>>> document.children[0].title.text = "Updated heading"

>>> print(dumps(document))
* Updated heading
```

## Top-level API

::: org_parser
    options:
      show_root_heading: true
      members:
        - load
        - loads
        - dump
        - dumps
