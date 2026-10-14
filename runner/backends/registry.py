from agents.errors import SprintRunnerError

from .herdr_backend import HerdrBackend
from .openrig_backend import OpenRigBackend
from .subprocess_backend import SubprocessBackend


class BackendRegistry:
    def __init__(self, backends=None):
        self._backends = dict(backends or {})

    def register(self, backend_type):
        self._backends[backend_type.name] = backend_type

    # Factories can declare compatibility by carrying a `supports_agent` attribute, e.g.
    # `factory.supports_agent = OpenRigBackend.supports_agent`.

    def supports_agent(self, name, agent_name):
        """True unless the backend type declares it cannot run `agent_name` (unknown names: False)."""
        backend_type = self._backends.get(name)
        if backend_type is None:
            return False
        check = getattr(backend_type, "supports_agent", None)
        if check is None:
            # A plain factory function says nothing about what its backend can run: be conservative,
            # so an optional default (the sprint backend) is never chosen on a guess.
            return False
        return bool(check(agent_name))

    def get(self, name, **kwargs):
        backend_type = self._backends.get(name)
        if backend_type is None:
            raise SprintRunnerError(
                "FAILED_UNKNOWN_BACKEND", f"Unknown execution backend: {name}"
            )
        return backend_type(**kwargs)

    @property
    def supported_backends(self):
        return tuple(sorted(self._backends))


default_backend_registry = BackendRegistry(
    {
        SubprocessBackend.name: SubprocessBackend,
        HerdrBackend.name: HerdrBackend,
        OpenRigBackend.name: OpenRigBackend,
    }
)
