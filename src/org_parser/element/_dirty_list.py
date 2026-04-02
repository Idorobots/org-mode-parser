"""Dirty-aware mutable list wrapper."""

from __future__ import annotations

from typing import TYPE_CHECKING, SupportsIndex, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

__all__ = ["DirtyList"]

_ItemT = TypeVar("_ItemT")


class DirtyList(list[_ItemT]):
    """List that invokes a callback after each in-place mutation."""

    def __init__(
        self,
        values: Iterable[_ItemT] = (),
        *,
        on_mutation: Callable[[DirtyList[_ItemT]], None] | None = None,
    ) -> None:
        super().__init__(values)
        self._on_mutation = on_mutation

    def _notify_mutation(self) -> None:
        callback = self._on_mutation
        if callback is None:
            return
        callback(self)

    def append(self, item: _ItemT) -> None:
        super().append(item)
        self._notify_mutation()

    def extend(self, items: Iterable[_ItemT]) -> None:
        super().extend(items)
        self._notify_mutation()

    def insert(self, index: SupportsIndex, item: _ItemT) -> None:
        super().insert(index, item)
        self._notify_mutation()

    def pop(self, index: SupportsIndex = -1) -> _ItemT:
        item = super().pop(index)
        self._notify_mutation()
        return item

    def remove(self, item: _ItemT) -> None:
        super().remove(item)
        self._notify_mutation()

    def clear(self) -> None:
        super().clear()
        self._notify_mutation()

    def reverse(self) -> None:
        super().reverse()
        self._notify_mutation()
