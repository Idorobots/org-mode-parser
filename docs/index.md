# Overview

This project implements a Python parser for Emacs Org-Mode files
providing nice semantic nodes in a hierarchical document tree. It's
based on [this Tree-Sitter
grammar](https://github.com/Idorobots/tree-sitter-org).

`org-parser` was created as an alternative to the wonderful, but
admitedly incomplete and unmaintained
[`orgparse`](https://github.com/karlicoss/orgparse/). The main
improvements on top of `orgparse` are:

- *Almost* complete feature set, including markup, blocks, tables and
  more niche constructs such as Babel calls.
- Fully mutable tree for easy edits that preserves original document
  whitespace & formatting.
- Better document error handling and reporting, useful for validation.

[See the documentation here.](https://idorobots.github.io/org-parser/)

# Installation

``` bash
pip install org-parser
```

# Features

- Semantic nodes with all the expected attributes

``` python
>>> from org_parser import loads
>>> doc = loads('''
... #+TITLE: Document
... #+AUTHOR: Idorobots
... :PROPERTIES:
... :name: value
... :END:
... An example document.
... * Heading 1
... ** Heading 2               :tag:
... *** Heading 3
... ''')
>>> doc.title
RichText('Document')
>>> doc.body
[BlankLine(), Paragraph(body=RichText('An example document.\n'))]
>>> doc.body_text
'\nAn example document.\n'
>>> doc.properties["name"]
RichText('value')
>>> len(doc.all_headings)
3
>>> doc.all_headings[1].tags
['tag']
```

- Structured traversal

``` python
>>> from org_parser import loads
>>> doc = loads('''
... * Heading 1
... ** Heading 2
... *** Heading 3
... ''')
>>> doc.children[0].title
RichText('Heading 1')
>>> doc.children[0].children[0].title
RichText('Heading 2')
>>> doc.children[0].children[0].parent.title == "Heading 1"
True
>>> doc.children[0].children[0].siblings
[]
```

- Original source whitespace and formatting preserved by default

``` python
>>> from org_parser import loads
>>> doc = loads('''
... #+TITLE: Original formatting
... * Heading 1
...   Indented section
...      remains indented 
...    in-tree.  
... ''')
>>> print(str(doc.children[0]))
* Heading 1
  Indented section
     remains indented 
   in-tree.  

>>> print(doc.render())

#+TITLE: Original formatting
* Heading 1
  Indented section
     remains indented 
   in-tree.  
```

- Fully mutable tree allowing dynamic edits

``` python
>>> from org_parser import loads
>>> from org_parser.element import Paragraph
>>> doc = loads('''
... #+TITLE: Document title
... * Heading 1
...   Body text.
... ''')
>>> doc.title
RichText('Document title')
>>> doc.title.text = "Another title"
>>> doc[0].body = [Paragraph.from_source("New *and* improved!")]
>>> doc[0].title.text = "Improved heading"
>>> print(doc.render())
#+TITLE: Another title

* Improved heading
New *and* improved!
```

- Org Table support

``` python
>>> from org_parser import loads
>>> doc = loads('''
... |Value|Double|
... |1| |
... |2| |
... |3| |
... ''')
>>> for r in doc.body[1].rows[1:]:
...   r[1].text = str(2 * int(r[0].text))
...   
>>> print(doc.render())

| Value | Double |
| 1     | 2      |
| 2     | 4      |
| 3     | 6      |
```

- Rich Text support

``` python
>>> from org_parser.text import RichText
>>> text = RichText.from_source("Supports *org-mode* /markup/ and inline_{objects}: <2026-03-29>")
>>> text
RichText('Supports *org-mode* /markup/ and inline_{objects}: <2026-03-29>')
>>> text.parts
[PlainText(text='Supports '), Bold(body=[PlainText(text='org-mode')]), PlainText(text=' '), Italic(body=[PlainText(text='markup')]), PlainText(text=' and inline'), Subscript(body=[PlainText(text='objects')], form='{}'), PlainText(text=': '), Timestamp(is_active=True, start_year=2026, start_month=3, start_day=29), PlainText(text='')]
```

- Error recovery

``` python
>>> from org_parser import loads
>>> doc = loads('''
... * Heading
... SCHEDULED: yesterday
... ''')
>>> doc[0].scheduled is None
True
>>> doc.errors
[ParseError(start_point=Point(row=2, column=0), end_point=Point(row=2, column=20), text='SCHEDULED: yesterday')]
```

Parsing <span class="spurious-link" target="examples/showcase.org">*this
file*</span> results in the following <span class="spurious-link"
target="examples/showcase.python">*Python object layout*</span>.
