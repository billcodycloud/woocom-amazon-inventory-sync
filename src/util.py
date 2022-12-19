from typing import Callable, Iterable, TypeVar

T = TypeVar('T')
U = TypeVar('U')


def find(pred: Callable[[T], bool], xs: Iterable[T]) -> T | None:
    """Returns the first element of `xs` that satisfies `pred`."""
    for x in xs:
        if pred(x):
            return x


def groupby_single(fn: Callable[[T], U], xs: Iterable[T]) -> dict[U, T]:
    return {fn(x): x for x in xs}
