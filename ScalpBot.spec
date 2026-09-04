# PyInstaller build specification for the local control-panel desktop app.
from pathlib import Path


project_root = Path(SPECPATH)

a = Analysis(
    [str(project_root / "scalp_bot" / "control_panel" / "__main__.py")],
    pathex=[str(project_root)],
    datas=[
        (str(project_root / "scalp_bot" / "control_panel" / "templates"), "scalp_bot/control_panel/templates"),
        (str(project_root / "scalp_bot" / "control_panel" / "static"), "scalp_bot/control_panel/static"),
        (str(project_root / "config"), "config"),
        (str(project_root / "data" / "sample_ohlcv.csv"), "data"),
    ],
    hiddenimports=["scalp_bot.control_panel.app"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ScalpBot",
    console=True,
)