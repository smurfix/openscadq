from __future__ import annotations

from pathlib import Path
from subprocess import run as spawn, DEVNULL
import io
import sys
from tempfile import NamedTemporaryFile
from contextlib import suppress, nullcontext

from buildscad import parse
from build123d import Mesher, Shape

class Res:
    tolerance = 0.001
    numeric = False
    no_add=False
    trace=False

    def __init__(self):
        self._models = {}
    def add(self, name, model):
        if model is None:
            return
        self._models[name] = model
    @property
    def models(self):
        for k,v in self._models.items():
            yield (v,k)
    def __getitem__(self, x):
        return self._models[x]
    def __contains__(self, x):
        return x in self._models
    def __len__(self):
        return len(self._models)

def testcase(i, may_skip=False):
    import tests.env_build123d as _env
    result = Res()
    params = {}
    run=True

    pyf = Path(f"tests/models/{i :03d}.py")
    if pyf.exists():
        py = pyf.read_text()
        pyc = compile(py, str(pyf), "exec")
        env2 = {}
        env2.update(_env.__dict__)
        exec(pyc, env2, env2)
        if "result" in env2:
            result.add("python",env2["result"]())
            result.numeric = True
        else:
            with suppress(KeyError):
                if may_skip and env2["skip"]:
                    import pytest
                    pytest.skip("'skip' is set")
            with suppress(KeyError):
                result.volume = env2["volume"]
            with suppress(KeyError):
                result.trace = env2["tracing"]
            with suppress(KeyError):
                result.tolerance = env2["tolerance"]
            with suppress(KeyError):
                result.no_add = env2["no_add"]
            with suppress(KeyError):
                params = env2["params"]
            with suppress(KeyError):
                run = env2["run"]
            try:
                res = env2["result"]
            except KeyError:
                try:
                    m2 = env2["work"]
                except KeyError:
                    res = None
                    for v in env2.values():
                        if not isinstance(v,Shape) or v._dim != 3:
                            continue
                        if res is None:
                            res = v
                        else:
                            res += v
                    assert res, "No Python results. Did you assign them to something?"
                    m2 = res
                else:
                    if m2 is not None:
                        m2 = m2(**params)
                result.add("python",m2)

    scadf = f"tests/models/{i :03d}.scad"
    env1 = parse(scadf)
    if result.numeric:
        m1 = env1["result"]
        result.add("parser", m1)
    else:
        with env1.tracing() if result.trace else nullcontext():
            if "work" in env1.static.mods:
                m1 = env1.mod("work", **params)
            else:
                m1 = env1.build()
            result.add("parser", m1)

        if "check" in env1.static.mods:
            m1x = env1.mod("check", **params)
            result.add("check", m1x)
 
    if run and not result.numeric:
        with NamedTemporaryFile(suffix=".stl", delete=not result.trace and "pytest" not in sys.modules) as tf,NamedTemporaryFile(suffix=".txt") as out:
            spawn(["openscad","--export-format=binstl", "-o",tf.name,scadf], check=True, stdin=DEVNULL, stdout=out, stderr=out, text=True)
            m3 = Mesher().read(tf.name)
            res = None
            for m in m3:
                if res is None:
                    res = m
                else:
                    res += m

            result.add("openscad",res)
            if result.trace:
                print(f"o_stl = Mesher().read({tf.name !r})")

    return result
