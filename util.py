import dataclasses
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, Iterable, Literal, Mapping, Optional, TypeVar


@dataclass
class Color:
    red: float
    green: float
    blue: float

    @classmethod
    def from_hex(cls, hex: str) -> 'Color':
        hex = hex.lstrip('#')
        return Color(*[int(hex[i:i+2], 16)/255 for i in range(0, 6, 2)])

    @classmethod
    def from_dict(cls, values: Dict[Literal['red', 'green', 'blue'], float]):
        return Color(red=values.get('red', 0.0), green=values.get('green', 0.0),
                     blue=values.get('blue', 0.0))

    def to_hex(self) -> str:
        return '#' + ''.join(format(int(i * 255), '02x') for i in dataclasses.astuple(self))

    def to_dict(self) -> str:
        return dataclasses.asdict(self)


T = TypeVar('T')


class Future(Generic[T]):
    def __init__(self):
        self._event = threading.Event()
        self._value: Optional[T] = None
        self._exception: Optional[BaseException] = None

    def set(self, value: T) -> None:
        self._value = value
        self._event.set()

    def set_exception(self, exception: BaseException) -> None:
        self._exception = exception
        self._event.set()

    def wait(self) -> T:
        self._event.wait()
        return self._value


def future(f: Callable[..., T], args: Optional[Iterable[Any]] = None,
           kwargs: Optional[Mapping[str, Any]] = None) -> Future[T]:
    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}
    future = Future()

    def do_f():
        try:
            result = f(*args, **kwargs)
        except BaseException as e:
            future.set_exception(e)
        else:
            future.set(result)

    threading.Thread(target=do_f).start()
    return future
