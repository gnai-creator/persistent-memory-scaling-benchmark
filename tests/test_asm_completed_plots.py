from persistent_memory_scaling.asm_completed_plots import _save


def test_completed_plot_module_imports() -> None:
    assert callable(_save)
