from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
PAINEL = str(Path(__file__).resolve().parent.parent / "painel.py")


@pytest.fixture(scope="module")
def app():
    return AppTest.from_file(PAINEL, default_timeout=180).run()


def test_painel_abre_sem_erros_e_mostra_os_indicadores(app):
    assert not app.exception
    assert [m.label for m in app.metric] == [
        "Custo da rede",
        "Rede na ponta",
        "Energia renovável",
        "Pico na rede",
        "Acima do limite",
        "Promessas de carga",
    ]


def test_assistente_responde_no_painel(app):
    app.chat_input[0].set_value("quanto economizamos hoje?").run()
    assert not app.exception
    respostas = [m.markdown[0].value for m in app.chat_message if m.name == "assistant"]
    assert respostas and r"R\$" in respostas[-1]  # escapado: o Markdown não vira fórmula


def test_mudar_a_instalacao_recalcula_sem_erros(app):
    app.sidebar.slider[1].set_value(0.0).run()  # sem bateria
    assert not app.exception
    app.sidebar.radio[0].set_value("A").run()
    assert not app.exception
