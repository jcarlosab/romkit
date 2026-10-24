from dataclasses import dataclass


@dataclass(frozen=True)
class PspLayout:
    game_directory: str = "PSP_GAME"
    parameter_file: str = "PSP_GAME/PARAM.SFO"
    boot_file: str = "PSP_GAME/SYSDIR/EBOOT.BIN"
