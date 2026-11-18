# bangumi.py 的测试（审计 2026-11-18）。
#
# 跑法（在仓库根）：
#   python3 -I -B -m unittest discover -s .github/tests
# （不加 -t .：.github 不是合法的包名，加了 unittest 会报 Start directory is not importable。）
#
# 只用标准库；不联网：request/resolve/subject/episodes 换成桩，断网也能跑。HOME、XDG_*、MIYU_* 都指到临时目录。
# 放在 .github/tests/ 而不是 tests/：打包会跳过 .github，测试不会进包。

import datetime as dt
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "bangumi.py"


def load():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("bangumi_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Sandbox(unittest.TestCase):
    """每条测试一个临时目录，环境里去掉所有 MIYU_*，网络函数先换成直接失败的桩。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("MIYU_", "XDG_"))}
        env.update(HOME=str(root / "home"), XDG_CONFIG_HOME=str(root / "cfg"),
                   XDG_CACHE_HOME=str(root / "xdg-cache"), XDG_STATE_HOME=str(root / "xdg-state"),
                   XDG_DATA_HOME=str(root / "xdg-data"))
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = root
        self.mod = load()
        self.calls = []

        def no_network(path, body=None, params=None):
            self.calls.append(path)
            raise AssertionError(f"测试里不该联网：{path}")

        self.mod.request = no_network

    def call(self, args):
        """照 main() 跑一次：stdin 喂 JSON，返回 (退出码, 输出)。"""
        out = io.StringIO()
        code = 0
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(args))), redirect_stdout(out):
            try:
                self.mod.main()
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue()

    def stub_subject(self, eps):
        self.mod.resolve = lambda query, subject_type: (1, [])
        self.mod.subject = lambda subject_id: {"id": 1, "name": "X", "name_cn": "某番"}
        self.mod.episodes = lambda subject_id: eps


class EpisodesWindow(Sandbox):
    # 审计 #178 bangumi（主人已定新行为）：未开播的番给公布的全部集数。
    # 现在 limit 窗口「结束在下一集要播的那集」，未开播时下一集是第 1 集，limit=12 只给 1 集。
    def test_unaired_show_lists_announced_episodes(self):
        first = dt.date.today() + dt.timedelta(days=30)
        eps = [{"ep": i + 1, "name": f"e{i + 1}", "airdate": (first + dt.timedelta(days=7 * i)).isoformat()}
               for i in range(12)]
        self.stub_subject(eps)
        code, out = self.call({"action": "episodes", "query": "X", "limit": 12, "format": "json"})
        self.assertEqual(code, 0, out)
        result = json.loads(out)
        self.assertEqual(result["total"], 12)
        self.assertEqual([e["ep"] for e in result["episodes"]], list(range(1, 13)))

    # 防改坏（现在就绿）：正在播的番 limit=3 照旧是「到下一集为止」的最后三集。
    def test_airing_show_window_ends_at_next_episode(self):
        today = dt.date.today()
        eps = [{"ep": i + 1, "airdate": (today - dt.timedelta(days=7 * (12 - i))).isoformat()} for i in range(12)]
        eps.append({"ep": 13, "airdate": (today + dt.timedelta(days=30)).isoformat()})
        self.stub_subject(eps)
        code, out = self.call({"action": "episodes", "query": "X", "limit": 3, "format": "json"})
        self.assertEqual(code, 0, out)
        self.assertEqual([e["ep"] for e in json.loads(out)["episodes"]], [11, 12, 13])


if __name__ == "__main__":
    unittest.main()
