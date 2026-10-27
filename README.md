# 番剧信息（miyu-scripts-bangumi）

给 Miyu 的脚本工具 `bangumi`：查番组计划（bgm.tv）。

- **放送表**：今天、明天、某一天或整周播什么，按评分排（评分人数不到 50 的排后面）。
- **搜索**：按名字搜动画、书、游戏、音乐、三次元条目。
- **条目**：评分、排名、标签、简介；动画还给出播到第几集、下一集哪天播。
- **剧集表**：给了 `limit` 时只列到下一集为止的最近 N 集，长篇（海贼王上千集）也不会刷屏。

## 参数

| 参数 | 说明 |
|---|---|
| `action` | `calendar`、`search`、`subject`、`episodes`；不写时有 `query` 就是 `subject`，没有就是 `calendar` |
| `query` | 条目名（中文译名或原名）或 bgm.tv 的条目 id；名字取最匹配的一个，其余列在后面 |
| `weekday` | 放送表用：`today`（默认）、`tomorrow`、`week`、`mon`–`sun`、`1`–`7`、`周一`–`周日` |
| `type` | `anime`（默认）、`book`、`game`、`music`、`real` |
| `limit` | 放送表每天几部、搜索几条（默认 8，至多 25）、剧集表几集 |
| `format` | `md`（默认）或 `json` |

## 依赖与注意

- 只用 Python 标准库，走 `api.bgm.tv` 的公开接口，不用登录。
- 放送表一天只取一次，存在 `MIYU_SCRIPT_CACHE_DIR`；没有缓存目录就每次现取。
- 「今天」按运行这台机器的本地日期算。
