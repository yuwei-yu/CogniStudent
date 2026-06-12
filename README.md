# CogniStudent

辅导员辨识学生比赛/训练桌面程序，使用 PySide6 + qt-material 构建 Windows GUI，可通过 GitHub Actions 打包为单文件 exe。

## 环境配置

- Python 3.9+
- Windows 打包建议使用 Python 3.11
- 安装依赖：

```bash
pip install -r requirements.txt
```

本地运行：

```bash
python src/main.py
```

## 数据目录

程序运行目录下固定使用 `resources/` 作为运行时数据根目录。首次启动会自动创建：

- `resources/admin_config.json`
- `resources/judge_config.json`

默认管理员账号为 `admin`，密码为 `admin123`。默认评委账号为 `judge`，密码为 `123`。如需修改，直接编辑对应 JSON 文件。

活动目录必须位于 `resources/` 下，例如：

```text
resources/
└── 测试辅导员大赛/
    ├── 张三-105018.xls
    ├── 张三-105018/
    │   ├── 3191621001.jpg
    │   └── 3191621002.png
    ├── 李四-205052.xls
    └── 李四-205052/
```

每名辅导员由一个同名 Excel 文件和一个同名照片文件夹组成，命名格式为 `姓名-工号`。辅导员登录时账号为姓名，密码为工号。

## Excel 字段

程序会校验并读取以下中文字段：

`学号`、`姓名`、`专业`、`政治面貌`、`担任职务`、`家庭住址`、`宿舍`、`家庭经济状况`、`心理健康状况`、`英语四六级`、`不及格科目`、`奖惩情况`

照片文件名应为 `学号.jpg`、`学号.jpeg` 或 `学号.png`。照片缺失会警告，但不阻止导入。

## 角色说明

管理员：

- 创建、删除活动
- 上传辅导员资料 zip
- 下载上传模板
- 勾选并保存本次比赛参赛名单到 `contest_config.json`
- 删除辅导员 Excel 和照片文件夹

辅导员：

- 选择活动后使用姓名和工号登录
- 可进行大海捞针、鱼目混珠、描述定位三类训练或比赛
- 训练模式默认开启，不计时并显示答案；关闭训练模式后启用计时
- 可保存本地成绩到当前活动的 `scores.json`

评委：

- 选择活动并使用评委账号登录
- 读取管理员设置的参赛名单；如果未设置，则使用活动下全部辅导员
- 启动环节、暂停/继续计时
- 根据口头回答逐信息点点击“正确/错误”累计分数
- 导出成绩 Excel 到 `resources/<活动名>_成绩汇总.xlsx`

## 上传模板

根目录的 `template.zip` 是用户可见模板。管理员界面点击“下载上传模板”会优先复制根目录模板；如果根目录模板不存在，会使用打包进 exe 的 `src/resources/template.zip` 后备模板。

上传资料 zip 可包含一个或多个辅导员，每个辅导员必须包含：

- `姓名-工号.xls` 或 `姓名-工号.xlsx`
- `姓名-工号/` 照片文件夹

程序会防止 zip 路径遍历，并在同名辅导员存在时询问覆盖或跳过。

## Windows 打包

本项目已配置 `.github/workflows/build.yml`，使用 `windows-latest` 自动打包：

```powershell
pyinstaller --onefile --windowed --name "CogniStudent" `
  --add-data "src/resources/template.zip;resources/template.zip" `
  --collect-all qt_material `
  src/main.py
```

打包产物会上传为 `CogniStudent-Windows` artifact。

## 常见问题

- Excel 列名错误：请按模板字段命名，或使用程序已兼容的常见别名，例如“学生姓名”“宿舍号”等。
- `.xls` 读取失败：确认安装了 `xlrd>=2.0`。
- 照片不显示：确认照片位于同名辅导员文件夹内，文件名与学号完全一致。
- 没有活动可选：使用管理员登录并创建活动，或手动在 `resources/` 下放置活动文件夹。
- 成绩排名为空：辅导员端或评委端需要先保存成绩。
