"""해석: 모든 파일의 FileSymbols → 호출·import 엣지와 해석 지표.

원칙: 확실할 때만 엣지를 만든다. 후보가 여럿이면(모호함) 추측하지 않고 센다.
호출 해석 순서(언어별 규칙은 아래 클래스 주석):
  같은 클래스·같은 파일 → import된 심볼 → (Java) 같은 패키지·와일드카드 import
이름이 프로젝트 안 어디에도 정의돼 있지 않은 호출(표준 라이브러리, 외부 패키지)은 `external`로 세고
해석 성공률의 분모에서 뺀다.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from codemap_worker.structure.model import CallSite, Definition, FileSymbols, ImportRef

RESOLVED = "resolved"
UNRESOLVED = "unresolved"  # 프로젝트 안에 같은 이름이 있는데 어느 것인지 못 찾음
AMBIGUOUS = "ambiguous"  # 후보가 둘 이상
EXTERNAL = "external"  # 프로젝트 안에 없는 이름

ClassKey = tuple[str, tuple[str, ...]]  # (파일 경로, 클래스 이름들)
_AMB = "ambiguous-type"


@dataclass
class Resolution:
    call_edges: Counter = field(default_factory=Counter)  # (caller_id, target_id) → 호출 횟수
    import_edges: set = field(default_factory=set)  # (source_id, target_id)
    counts: Counter = field(default_factory=Counter)
    unresolved_names: Counter = field(default_factory=Counter)  # 해석 못 한 호출의 "수신자.이름"
    by_file: dict = field(default_factory=lambda: defaultdict(Counter))  # 파일 → 결과별 호출 수


def resolve(files: list[FileSymbols]) -> Resolution:
    return _Resolver(files).run()


class _Resolver:
    def __init__(self, files: list[FileSymbols]) -> None:
        self.files = sorted(files, key=lambda f: f.path)
        self.by_path = {f.path: f for f in self.files}
        self.def_by_id: dict[str, Definition] = {}
        self.by_name: dict[str, list[Definition]] = defaultdict(list)
        self.members: dict[ClassKey, dict[str, list[Definition]]] = defaultdict(lambda: defaultdict(list))
        self.toplevel: dict[str, dict[str, list[Definition]]] = defaultdict(lambda: defaultdict(list))
        self.classes_by_name: dict[str, set[ClassKey]] = defaultdict(set)
        self.rep: dict[str, str] = {}  # 파일 → 대표 노드(가장 먼저 정의된 것)
        self.overload_guesses = 0

        for f in self.files:
            ordered = sorted(f.definitions, key=lambda d: (d.start_line, d.id))
            if ordered:
                self.rep[f.path] = ordered[0].id
            for d in f.definitions:
                self.def_by_id[d.id] = d
                self.by_name[d.name].append(d)
                if d.container:
                    self.members[(f.path, d.container)][d.name].append(d)
                    for k in range(1, len(d.container) + 1):
                        self.classes_by_name[d.container[k - 1]].add((f.path, d.container[:k]))
                else:
                    self.toplevel[f.path][d.name].append(d)

        self._index_python()
        self._index_java()

    # ---------- 색인 ----------

    def _index_python(self) -> None:
        self.py_suffix: dict[str, set[str]] = defaultdict(set)
        self.py_components: set[str] = set()
        for f in self.files:
            if f.language != "python":
                continue
            parts = f.path.removesuffix(".py").split("/")
            self.py_components.update(parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):
                self.py_suffix[".".join(parts[i:])].add(f.path)

    def _index_java(self) -> None:
        self.java_types: dict[str, ClassKey] = {}
        self.java_packages: set[str] = set()
        self.java_class_keys: set[ClassKey] = set()
        for f in self.files:
            if f.language != "java":
                continue
            pkg = f.package or ""
            self.java_packages.add(pkg)
            stem = f.path.rsplit("/", 1)[-1].removesuffix(".java")
            tops = {d.container[0] for d in f.definitions if d.container} | {stem}
            for name in sorted(tops):
                self.java_types.setdefault(_fqn(pkg, (name,)), (f.path, (name,)))
                self.java_class_keys.add((f.path, (name,)))
            for d in f.definitions:
                for k in range(1, len(d.container) + 1):
                    key = (f.path, d.container[:k])
                    self.java_types.setdefault(_fqn(pkg, d.container[:k]), key)
                    self.java_class_keys.add(key)

    def py_module_file(self, dotted: str, from_path: str | None = None) -> str | None:
        """점으로 구분한 모듈 이름 → 파일. 후보가 여럿이면 가까운 폴더의 것을 고른다(같은 거리면 포기)."""
        cands = self.py_suffix.get(dotted)
        if not cands:
            return None
        if len(cands) == 1:
            return next(iter(cands))
        # 실제 Python은 소스 루트(sys.path)에서 찾으므로, 이름 앞에 붙은 폴더가 가장 적은 후보가 진짜다.
        # (`src/flask/__init__.py`가 `tests/.../inner2/flask.py`보다 우선)
        extra = {p: _py_dotted(p).count(".") - dotted.count(".") for p in cands}
        best = [p for p in cands if extra[p] == min(extra.values())]
        if len(best) == 1:
            return best[0]
        if from_path is None:
            return None
        scored = sorted(((_common_dirs(p, from_path), p) for p in best), reverse=True)
        return scored[0][1] if scored[0][0] > scored[1][0] else None

    def py_relative(self, from_path: str, level: int, module: str) -> str | None:
        """상대 import(`from ..pkg import x`)가 가리키는 파일. 점 1개 = 이 파일이 든 폴더."""
        dirs = from_path.split("/")[:-1]
        if level - 1 > len(dirs):
            return None
        base = "/".join(dirs[: len(dirs) - (level - 1)] + (module.split(".") if module else []))
        candidates = [f"{base}.py", f"{base}/__init__.py"] if base else ["__init__.py"]
        return next((c for c in candidates if c in self.by_path), None)

    # ---------- 실행 ----------

    def run(self) -> Resolution:
        out = Resolution()
        # 0단계: Python 파일마다 import 범위를 만들어 둔다 (다른 파일의 재내보내기를 따라가려면 먼저 필요하다)
        self.scopes: dict[str, _PyScope] = {}
        for f in self.files:
            if f.language == "python":
                sc = _PyScope()
                self._py_imports(f, sc, Resolution())
                self.scopes[f.path] = sc
        # 1단계: import 엣지와 호출 해석
        for f in self.files:
            if f.language == "python":
                self._py_imports(f, _PyScope(), out)
                scope: _PyScope | _JavaScope = self.scopes[f.path]
            else:
                scope = _JavaScope()
                self._java_imports(f, scope, out)
            for call in f.calls:
                caller = self.def_by_id[call.caller_id]
                if f.language == "python":
                    outcome, target = self._py_call(f, scope, caller, call)
                else:
                    outcome, target = self._java_call(f, scope, caller, call)
                self._record(out, call, caller, outcome, target)
        out.counts["callOverloadGuess"] = self.overload_guesses
        return out

    def _record(self, out: Resolution, call: CallSite, caller: Definition, outcome: str, target: str | None) -> None:
        out.by_file[_path_of(caller.id)][outcome if target is not None or outcome != RESOLVED else UNRESOLVED] += 1
        if outcome == RESOLVED and target is not None:
            out.counts["callResolved"] += 1
            if target != caller.id:  # 재귀는 엣지로 만들지 않는다
                out.call_edges[(caller.id, target)] += 1
            return
        if outcome == UNRESOLVED:
            out.counts["callUnresolved"] += 1
        elif outcome == AMBIGUOUS:
            out.counts["callAmbiguous"] += 1
        else:
            out.counts["callExternal"] += 1
            return
        out.unresolved_names[_call_label(call)] += 1

    def _miss(self, call: CallSite) -> tuple[str, str | None]:
        """찾지 못했을 때: 프로젝트에 같은 이름이 있으면 해석 실패, 없으면 외부 호출."""
        known = call.name in self.by_name or call.name in self.classes_by_name
        return (UNRESOLVED if known else EXTERNAL), None

    def _pick(self, defs: list[Definition], arity: int | None = None) -> tuple[str, str | None]:
        """후보 중 하나를 고른다. 인자 수로 좁히고, 그래도 여럿이면:
        - 모두 같은 클래스의 오버로드이면 소스 순서로 첫 번째에 연결한다(어느 클래스의 메서드인지는 확실하다).
          이렇게 고른 횟수를 `callOverloadGuess`로 센다.
        - 서로 다른 클래스·파일의 후보이면 모호함이다.
        """
        if not defs:
            return UNRESOLVED, None
        pool = defs
        if arity is not None and len(defs) > 1:
            exact = [d for d in defs if d.params == arity]
            pool = exact or defs
        if len(pool) == 1:
            return RESOLVED, pool[0].id
        if len({(_path_of(d.id), d.container) for d in pool}) == 1:
            self.overload_guesses += 1
            return RESOLVED, min(pool, key=lambda d: (d.start_line, d.id)).id
        return AMBIGUOUS, None

    # ---------- Python ----------

    def _py_imports(self, f: FileSymbols, sc: "_PyScope", out: Resolution) -> None:
        src = self.rep.get(f.path)
        for imp in f.imports:
            if imp.level == 0 and not imp.names and not imp.is_wildcard:
                target_file = self.py_module_file(imp.module, f.path)
                if target_file:
                    sc.dotted[imp.module] = target_file
                    if imp.alias:
                        sc.module_alias[imp.alias] = target_file
                    else:
                        top = imp.module.split(".")[0]
                        sc.module_alias[top] = self.py_module_file(top, f.path) or ""
                elif imp.module.split(".")[0] not in self.py_components:
                    sc.external.add(imp.alias or imp.module.split(".")[0])  # `import numpy as np`
                self._import_edge(out, src, self.rep.get(target_file) if target_file else None,
                                  external=target_file is None and imp.module.split(".")[0] not in self.py_components)
                continue

            mod_file = (self.py_relative(f.path, imp.level, imp.module) if imp.level
                        else self.py_module_file(imp.module, f.path))
            external = mod_file is None and imp.level == 0 and imp.module.split(".")[0] not in self.py_components
            if imp.is_wildcard:
                if mod_file:
                    sc.wildcards.append(mod_file)
                self._import_edge(out, src, self.rep.get(mod_file) if mod_file else None, external=external)
                continue
            for name, alias in imp.names:
                local = alias or name
                sub = self._py_submodule(f.path, imp, name)
                sc.symbols[local] = (mod_file, name, sub)
                if external and sub is None:
                    sc.external.add(local)  # `from os import path`
                target = None
                if mod_file:
                    defs = self._py_symbol_defs(mod_file, name)
                    target = defs[0].id if len(defs) == 1 else None
                target = target or (self.rep.get(sub) if sub else None) or (self.rep.get(mod_file) if mod_file else None)
                self._import_edge(out, src, target, external=external and sub is None)

    def _py_submodule(self, from_path: str, imp: ImportRef, name: str) -> str | None:
        joined = f"{imp.module}.{name}" if imp.module else name
        if imp.level:
            return self.py_relative(from_path, imp.level, joined)
        return self.py_module_file(joined, from_path)

    def _import_edge(self, out: Resolution, src: str | None, target: str | None, external: bool) -> None:
        if target is None:
            out.counts["importExternal" if external else "importUnresolved"] += 1
            return
        out.counts["importResolved"] += 1
        if src is not None and src != target:
            out.import_edges.add((src, target))

    def _py_has_class(self, path: str, name: str) -> bool:
        return (path, (name,)) in self.classes_by_name.get(name, set())

    def _py_find(self, path: str, name: str, depth: int = 0) -> tuple[str, str] | None:
        """모듈 `path`에서 `name`(함수 또는 클래스)이 정의된 곳. 다시 내보낸 이름(from .app import Flask)도 따라간다."""
        if self.toplevel.get(path, {}).get(name) or self._py_has_class(path, name):
            return path, name
        entry = self.scopes[path].symbols.get(name) if depth < 3 and path in self.scopes else None
        if entry and entry[0] and entry[0] != path:
            return self._py_find(entry[0], entry[1], depth + 1)
        return None

    def _py_symbol_defs(self, path: str, name: str) -> list[Definition]:
        """모듈 안의 함수 `name`, 또는 클래스 `name`의 `__init__`."""
        hit = self._py_find(path, name)
        if hit is None:
            return []
        funcs = self.toplevel.get(hit[0], {}).get(hit[1], [])
        return funcs or self.members.get((hit[0], (hit[1],)), {}).get("__init__", [])

    def _py_symbol_call(self, path: str, name: str, call: CallSite) -> tuple[str, str | None] | None:
        """모듈의 심볼을 호출했을 때의 해석. 그 모듈에 없으면 None."""
        hit = self._py_find(path, name)
        if hit is None:
            return None
        funcs = self.toplevel.get(hit[0], {}).get(hit[1], [])
        return self._pick(funcs) if funcs else self._class_ctor(hit[0], hit[1], call)

    def _py_call(self, f: FileSymbols, sc: "_PyScope", caller: Definition, call: CallSite) -> tuple[str, str | None]:
        name, recv = call.name, call.receiver

        if recv is None:
            funcs = self.toplevel.get(f.path, {}).get(name, [])
            if funcs:
                return self._pick(funcs)
            if self._py_has_class(f.path, name):
                return self._class_ctor(f.path, name, call)
            if name in sc.external:
                return EXTERNAL, None
            if name in sc.symbols:
                mod_file, sym, _sub = sc.symbols[name]
                hit = self._py_symbol_call(mod_file, sym, call) if mod_file else None
                return hit or self._miss(call)
            hits = [d for w in sc.wildcards for d in self._py_symbol_defs(w, name)]
            return self._pick(hits) if hits else self._miss(call)

        if recv in ("self", "cls"):
            if not caller.container:
                return self._miss(call)
            defs = self.members.get((f.path, caller.container), {}).get(name, [])
            return self._pick(defs) if defs else self._miss(call)

        if recv == "":
            return self._miss(call)
        if recv.split(".")[0] in sc.external:
            return EXTERNAL, None  # np.array(), os.path.join() 등 외부 라이브러리

        # 수신자가 모듈인가
        mod_file = sc.dotted.get(recv)
        if mod_file is None and "." not in recv:
            mod_file = sc.module_alias.get(recv) or None
        if mod_file is None and "." not in recv and recv in sc.symbols and sc.symbols[recv][2]:
            mod_file = sc.symbols[recv][2]  # `from pkg import util`의 util이 하위 모듈인 경우
        if mod_file is None and "." in recv and recv.split(".")[0] in sc.module_alias:
            mod_file = self.py_module_file(recv, f.path)
        if mod_file:
            return self._py_symbol_call(mod_file, name, call) or self._miss(call)

        # 수신자가 클래스인가 (정적·클래스 메서드 호출, `Foo.bar()`)
        if "." not in recv:
            key: ClassKey | None = None
            if self._py_has_class(f.path, recv):
                key = (f.path, (recv,))
            elif recv in sc.symbols and sc.symbols[recv][0]:
                hit = self._py_find(sc.symbols[recv][0], sc.symbols[recv][1])
                if hit and self._py_has_class(*hit):
                    key = (hit[0], (hit[1],))
            if key is not None:
                defs = self.members.get(key, {}).get(name, [])
                return self._pick(defs) if defs else self._miss(call)
        return self._miss(call)

    def _class_ctor(self, path: str, cls: str, call: CallSite) -> tuple[str, str | None]:
        inits = self.members.get((path, (cls,)), {}).get("__init__", [])
        if inits:
            return self._pick(inits)
        return EXTERNAL, None  # 생성자를 직접 쓰지 않은 클래스(dataclass 등)는 연결할 노드가 없다

    # ---------- Java ----------

    def _java_imports(self, f: FileSymbols, sc: "_JavaScope", out: Resolution) -> None:
        sc.package = f.package or ""
        for scope, var, typ in f.var_types:
            if scope.startswith("class:"):
                sc.fields.setdefault(tuple(scope[6:].split(".")), {})[var] = typ
            else:
                sc.locals.setdefault(scope, {})[var] = typ
        src = self.rep.get(f.path)
        for imp in f.imports:
            if imp.is_wildcard:
                (sc.static_wildcards if imp.is_static else sc.wildcards).append(imp.module)
                out.counts["importWildcard"] += 1
                continue
            if imp.is_static:
                member = imp.names[0][0]
                sc.static_members.setdefault(member, []).append(imp.module)
                key = self.java_types.get(imp.module)
                target = None
                if key:
                    defs = self.members.get(key, {}).get(member, [])
                    target = defs[0].id if len(defs) == 1 else self.rep.get(key[0])
                self._import_edge(out, src, target, external=key is None and self._java_external(imp.module.rpartition(".")[0]))
                continue
            sc.single_imports[imp.module.rpartition(".")[2]] = imp.module
            key = self.java_types.get(imp.module)
            self._import_edge(out, src, self.rep.get(key[0]) if key else None,
                              external=key is None and self._java_external(imp.module.rpartition(".")[0]))

    def _java_external(self, pkg: str) -> bool:
        """이 패키지가 프로젝트의 어떤 패키지와도 겹치지 않으면 외부 라이브러리다."""
        return not any(p == pkg or p.startswith(pkg + ".") or pkg.startswith(p + ".") for p in self.java_packages if p)

    def _java_type(self, f: FileSymbols, sc: "_JavaScope", name: str, container: tuple[str, ...]):
        """이름 → 클래스(파일, 클래스 이름들). 없으면 None, 후보가 여럿이면 _AMB."""
        if "." in name:
            hit = self.java_types.get(name)
            if hit:
                return hit
            head, _, rest = name.partition(".")
            base = self._java_type(f, sc, head, container)
            if isinstance(base, tuple):
                cand = (base[0], (*base[1], *rest.split(".")))
                if cand in self.java_class_keys:
                    return cand
            return None
        for k in range(len(container), 0, -1):  # 감싸는 클래스 안에 선언된 중첩 클래스
            key = (f.path, (*container[:k], name))
            if key in self.java_class_keys:
                return key
        if (f.path, (name,)) in self.java_class_keys:
            return (f.path, (name,))
        same_file = sorted(k for k in self.classes_by_name.get(name, ()) if k[0] == f.path)
        if same_file:
            return same_file[0]
        if name in sc.single_imports:
            return self.java_types.get(sc.single_imports[name])
        hit = self.java_types.get(_fqn(sc.package, (name,)))
        if hit:
            return hit
        hits = {self.java_types[w + "." + name] for w in sc.wildcards if (w + "." + name) in self.java_types}
        if len(hits) == 1:
            return next(iter(hits))
        return _AMB if hits else None

    def _java_call(self, f: FileSymbols, sc: "_JavaScope", caller: Definition, call: CallSite) -> tuple[str, str | None]:
        name, recv = call.name, call.receiver
        container = caller.container

        if call.is_constructor:
            key = self._java_type(f, sc, name, container)
            if key == _AMB:
                return AMBIGUOUS, None
            if key is None:
                return self._miss(call)
            ctors = self.members.get(key, {}).get(key[1][-1], [])
            if not ctors:
                return EXTERNAL, None  # 기본 생성자만 있는 클래스는 연결할 노드가 없다
            return self._pick(ctors, call.arity)

        if recv is None:
            for k in range(len(container), 0, -1):  # 안쪽 클래스부터 바깥 클래스 순서
                defs = self.members.get((f.path, container[:k]), {}).get(name, [])
                if defs:
                    return self._pick(defs, call.arity)
            for cls_name in sc.static_members.get(name, []):
                key = self.java_types.get(cls_name)
                defs = self.members.get(key, {}).get(name, []) if key else []
                if defs:
                    return self._pick(defs, call.arity)
            for cls_name in sc.static_wildcards:
                key = self.java_types.get(cls_name)
                defs = self.members.get(key, {}).get(name, []) if key else []
                if defs:
                    return self._pick(defs, call.arity)
            return self._miss(call)

        if recv == "this":
            defs = self.members.get((f.path, container), {}).get(name, []) if container else []
            return self._pick(defs, call.arity) if defs else self._miss(call)

        if recv in ("", "super"):
            return self._miss(call)

        # 변수·필드로 부른 호출: 선언된 타입으로 찾는다 (`Gson gson; gson.toJson()`)
        var = recv.removeprefix("this.")
        if "." not in var:
            typ = self._java_var_type(sc, caller, var, fields_only=recv.startswith("this."))
            if typ is not None:
                key = self._java_type(f, sc, typ, container)
                if key == _AMB:
                    return AMBIGUOUS, None
                if key is None:
                    return EXTERNAL, None  # 변수의 타입이 프로젝트 밖(String, List, StringBuilder 등)
                defs = self.members.get(key, {}).get(name, [])
                return self._pick(defs, call.arity) if defs else self._miss(call)

        key = self._java_type(f, sc, recv, container)  # 클래스 이름으로 부른 정적 메서드
        if key == _AMB:
            return AMBIGUOUS, None
        if key is not None:
            defs = self.members.get(key, {}).get(name, [])
            return self._pick(defs, call.arity) if defs else self._miss(call)
        if self._java_external_receiver(recv):
            return EXTERNAL, None  # Arrays.asList(), System.out.println(), java.util.Collections.sort()
        return self._miss(call)

    def _java_external_receiver(self, recv: str) -> bool:
        """변수가 아닌 이름(대문자로 시작하는 타입 이름, 패키지 경로)이 프로젝트 밖을 가리키는가."""
        head = recv.split(".")[0]
        if head[:1].isupper():
            return True
        # java.util.Collections처럼 소문자 패키지로 시작하면, 패키지 부분이 프로젝트와 겹치지 않을 때 외부다
        segments = recv.split(".")
        pkg = ".".join(seg for seg in segments[: next((i for i, x in enumerate(segments) if x[:1].isupper()), 0)])
        return bool(pkg) and self._java_external(pkg)

    @staticmethod
    def _java_var_type(sc: "_JavaScope", caller: Definition, var: str, fields_only: bool = False) -> str | None:
        """지역 변수·파라미터 → 바깥쪽 클래스 필드 순서로 선언 타입을 찾는다."""
        if not fields_only and var in sc.locals.get(caller.id, {}):
            return sc.locals[caller.id][var]
        for k in range(len(caller.container), 0, -1):
            typ = sc.fields.get(caller.container[:k], {}).get(var)
            if typ:
                return typ
        return None


@dataclass
class _PyScope:
    module_alias: dict[str, str] = field(default_factory=dict)  # 지역 이름 → 모듈 파일 ("" = 못 찾음)
    dotted: dict[str, str] = field(default_factory=dict)  # `import a.b.c`의 a.b.c → 파일
    symbols: dict[str, tuple] = field(default_factory=dict)  # 지역 이름 → (모듈 파일, 심볼, 하위 모듈 파일)
    wildcards: list[str] = field(default_factory=list)
    external: set[str] = field(default_factory=set)  # 외부 라이브러리에서 가져온 지역 이름


@dataclass
class _JavaScope:
    package: str = ""
    single_imports: dict[str, str] = field(default_factory=dict)  # 단순 이름 → FQN
    wildcards: list[str] = field(default_factory=list)  # 패키지
    static_members: dict[str, list[str]] = field(default_factory=dict)  # 메서드 이름 → [클래스 FQN]
    static_wildcards: list[str] = field(default_factory=list)  # 클래스 FQN
    locals: dict[str, dict[str, str]] = field(default_factory=dict)  # 정의 ID → {변수·파라미터: 선언 타입}
    fields: dict[tuple[str, ...], dict[str, str]] = field(default_factory=dict)  # 클래스 → {필드: 선언 타입}


def _call_label(call: CallSite) -> str:
    """해석 실패 목록에 보여 줄 이름: `수신자.이름`, 수신자가 복잡한 식이면 `?.이름`."""
    if call.receiver is None:
        return call.name
    return f"{call.receiver or '?'}.{call.name}"


def _path_of(def_id: str) -> str:
    return def_id.split("::", 1)[0]


def _fqn(pkg: str, names: tuple[str, ...]) -> str:
    return ".".join(([pkg] if pkg else []) + list(names))


def _py_dotted(path: str) -> str:
    parts = path.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _common_dirs(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a.split("/")[:-1], b.split("/")[:-1], strict=False):
        if x != y:
            break
        n += 1
    return n
