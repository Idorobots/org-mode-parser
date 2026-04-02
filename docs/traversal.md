# Tree traversal

`Document` and `Heading` form a tree:

- `Document` is the root node.
- `Document.children` contains only top-level headings.
- Each `Heading` has a `parent` and `children` list.
- `Document` also exposes `all_headings` for flattened traversal.

## Parent and children

```python
>>> from org_parser import loads

>>> document = loads('''
... * Project
... ** TODO API docs
... ** DONE Changelog
... * Personal
... ''')

>>> [heading.title_text for heading in document.children]
['Project', 'Personal']
>>> document[1].parent.title_text
'Project'
>>> [child.title_text for child in document[0].children]
['API docs', 'Changelog']
```

## Root and leaf checks

Use `is_root` and `is_leaf` to quickly reason about where you are in the tree.

```python
>>> from org_parser import loads

>>> document = loads('''
... * Top
... ** Child
... ''')

>>> document.is_root
True
>>> document.is_leaf
False
>>> document[0].is_root
False
>>> document[1].is_leaf
True
```

## Sequence interface

`Document` behaves like a sequence of all headings in file order.

```python
>>> from org_parser import loads

>>> document = loads('''
... * H1
... ** H1.1
... * H2
... ''')

>>> len(document)
3
>>> document[0].title_text
'H1'
>>> document[1].title_text
'H1.1'
>>> [heading.title_text for heading in document]
['H1', 'H1.1', 'H2']
```

`Heading` also behaves like a sequence, but only for direct child headings.

```python
>>> from org_parser import loads

>>> document = loads('''
... * Parent
... ** Child 1
... ** Child 2
... ''')

>>> parent = document[0]
>>> len(parent)
2
>>> parent[0].title_text
'Child 1'
>>> [child.title_text for child in parent]
['Child 1', 'Child 2']
```

## Traversal helpers

Use these helpers when walking or inspecting the tree:

- `heading.document`: jump back to the owning `Document`.
- `heading.level`: heading depth (`*` = 1, `**` = 2, ...).
- `document.all_headings`: flattened list in file order.

```python
>>> from org_parser import loads

>>> document = loads('''
... * H1
... ** H1.1
... ** H1.2
... * H2
... ''')

>>> document[2].document is document
True
>>> [heading.level for heading in document]
[1, 2, 2, 1]
>>> [heading.title_text for heading in document.all_headings]
['H1', 'H1.1', 'H1.2', 'H2']
>>> [heading.title_text for heading in document[:]]
['H1', 'H1.1', 'H1.2', 'H2']
```

## Siblings

Use `heading.siblings` to access other headings under the same parent.

```python
>>> from org_parser import loads

>>> document = loads('''
... * Roadmap
... ** Phase 1
... ** Phase 2
... ''')

>>> document[0].siblings
[]
>>> [heading.title_text for heading in document[1].siblings]
['Phase 2']
```
