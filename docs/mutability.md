# Mutability

`org-parser` keeps a mutable semantic tree. You can edit document fields,
heading fields, and element lists directly, then serialize back to Org text.

## Dirty flags

Every major semantic node tracks whether it has been mutated:

- `Document.dirty`
- `Heading.dirty`
- `Element.dirty`
- `RichText.dirty`
- `Timestamp.dirty`

Mutating a child object marks that object dirty and bubbles the dirty flag up
to its parent chain.

```python
>>> from org_parser import loads

>>> document = loads("* TODO Task\n")
>>> document.dirty, document[0].dirty
(False, False)

>>> document[0].title = "Updated task"
>>> document.dirty, document[0].dirty
(True, True)
```

## Preserving source formatting by default

When a parsed tree is still clean (`dirty == False`), rendering returns the
original source slices, including the original formatting and ordering.

```python
>>> from org_parser import loads

>>> document = loads("""Some text.
... #+TITLE: Title
... More text
... """)
>>> document.render()
'Some text.\n#+TITLE: Title\nMore text\n'
```

## Reconstructed output when dirty

Once the tree is dirty, output is reconstructed from semantic fields rather
than copied from parse-tree source slices.

```python
>>> from org_parser import loads

>>> document = loads("""Some text.
... #+TITLE: Title
... More text
... """)
>>> document.mark_dirty()
>>> document.render()
'#+TITLE: Title\nSome text.\nMore text\n'
```

## `reformat()` operation

Use `reformat()` to force a subtree into scratch-built rendering style.
This marks the subtree dirty and normalizes output according to render logic.

```python
>>> from org_parser import loads

>>> document = loads("""* Heading 1
... ** Heading 2
... CLOSED: <2025-10-10>
... SCHEDULED: <2025-10-10>
... """)
>>> document.reformat()
>>> print(document.render())
* Heading 1
** Heading 2
SCHEDULED: <2025-10-10> CLOSED: <2025-10-10>
```

## `DirtyList` wrapper

List-like properties such as `document.children`, `document.body`,
`heading.children`, and `heading.body` return a `DirtyList` wrapper.

`DirtyList` behaves like a regular mutable list, but each in-place mutation
(`append`, `insert`, `pop`, `remove`, `clear`, `reverse`, and `extend`) runs an
internal callback that updates ownership/structure and marks parents dirty.

```python
>>> from org_parser import loads

>>> document = loads("* Parent\n")
>>> document.dirty
False

>>> child = loads("* Child\n")[0]
>>> document[0].children.append(child)
>>> document.dirty
True
>>> document[1].heading_text
'** Child'
```

```python
>>> from org_parser import loads
>>> from org_parser.element import Paragraph

>>> heading = loads("* TODO Task\n")[0]
>>> heading.body.append(Paragraph.from_source("Extra details"))
>>> heading.dirty, heading.parent.dirty
(True, True)
>>> heading.render()
'* TODO Task\nExtra details\n'
```
