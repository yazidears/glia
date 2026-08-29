import argparse
import json
from collections.abc import Iterator
from pathlib import Path

TRAIN_SIZE = 120
EVAL_SIZE = 24

LocalizedValue = tuple[str, str, str]

SUBJECTS: list[LocalizedValue] = [
    ("observatori brutalista", "observatorio brutalista", "brutalist observatory"),
    ("ballarina sota la pluja", "bailarina bajo la lluvia", "dancer in the rain"),
    ("mercat nocturn", "mercado nocturno", "night market"),
    ("robot jardiner", "robot jardinero", "gardening robot"),
    ("biblioteca submarina", "biblioteca submarina", "underwater library"),
    ("tren travessant el desert", "tren cruzando el desierto", "train crossing the desert"),
    ("taller de ceràmica", "taller de cerámica", "pottery workshop"),
    ("far sobre un penya-segat", "faro sobre un acantilado", "lighthouse on a cliff"),
    ("astronauta entre flors", "astronauta entre flores", "astronaut among flowers"),
    ("hotel abandonat", "hotel abandonado", "abandoned hotel"),
    ("bosc de vidre", "bosque de cristal", "glass forest"),
    ("músic en un terrat", "músico en una azotea", "musician on a rooftop"),
]
MOODS: list[LocalizedValue] = [
    ("fred", "frío", "cold"),
    ("melancòlic", "melancólico", "melancholic"),
    ("juganer", "juguetón", "playful"),
    ("serè", "sereno", "serene"),
    ("misteriós", "misterioso", "mysterious"),
    ("càlid", "cálido", "warm"),
    ("èpic", "épico", "epic"),
    ("íntim", "íntimo", "intimate"),
]
STYLES: list[LocalizedValue] = [
    ("brutalista", "brutalista", "brutalist"),
    ("surrealista", "surrealista", "surrealist"),
    ("editorial", "editorial", "editorial"),
    ("minimalista", "minimalista", "minimalist"),
    ("cinematogràfic", "cinematográfico", "cinematic"),
    ("vintage", "vintage", "vintage"),
    ("abstracte", "abstracto", "abstract"),
    ("documental", "documental", "documentary"),
]
PALETTES: list[LocalizedValue] = [
    ("blau cobalt", "azul cobalto", "cobalt blue"),
    ("ambre i negre", "ámbar y negro", "amber and black"),
    ("verd molsa", "verde musgo", "moss green"),
    ("rosa pàl·lid", "rosa pálido", "pale pink"),
    ("vermell intens", "rojo intenso", "deep red"),
    ("blanc i gris", "blanco y gris", "white and grey"),
    ("taronja cremat", "naranja quemado", "burnt orange"),
    ("tons pastel", "tonos pastel", "pastel tones"),
]
COMPOSITIONS: list[LocalizedValue] = [
    ("pla general simètric", "plano general simétrico", "symmetrical wide shot"),
    ("primer pla lateral", "primer plano lateral", "side close-up"),
    ("vista zenital", "vista cenital", "overhead view"),
    ("perspectiva de contrapicat", "perspectiva en contrapicado", "low-angle perspective"),
    ("subjecte descentrat", "sujeto descentrado", "off-centre subject"),
    ("composició en capes", "composición en capas", "layered composition"),
]
MEDIUMS: list[LocalizedValue] = [
    ("fotografia", "fotografía", "photograph"),
    ("pintura", "pintura", "painting"),
    ("il·lustració", "ilustración", "illustration"),
    ("render 3D", "render 3D", "3d render"),
    ("collage", "collage", "collage"),
    ("fotograma de pel·lícula", "fotograma de película", "film still"),
]
ERAS: list[LocalizedValue] = [
    ("anys 1920", "años 1920", "1920s"),
    ("anys 1970", "años 1970", "1970s"),
    ("edat mitjana", "edad media", "middle ages"),
    ("futur proper", "futuro cercano", "near future"),
    ("barroc", "barroco", "baroque"),
    ("actualitat", "actualidad", "present day"),
]


def build_examples() -> list[dict[str, object]]:
    examples: list[dict[str, object]] = []
    for index in range(TRAIN_SIZE + EVAL_SIZE):
        language = index % 3
        concept = index // 3
        subject = SUBJECTS[concept % len(SUBJECTS)][language]
        mood = MOODS[(concept * 3) % len(MOODS)][language]
        style = STYLES[(concept * 5 + 1) % len(STYLES)][language]
        palette = PALETTES[(concept * 7 + 2) % len(PALETTES)][language]
        composition = COMPOSITIONS[(concept * 5 + 3) % len(COMPOSITIONS)][language]
        medium = MEDIUMS[(concept * 5 + 4) % len(MEDIUMS)][language]
        era = ERAS[(concept * 7 + 1) % len(ERAS)][language]
        text = _render_text(
            index=index,
            subject=subject,
            mood=mood,
            style=style,
            palette=palette,
            composition=composition,
            medium=medium,
            era=era,
        )
        examples.append(
            {
                "text": text,
                "json_structures": [
                    {
                        "visual_direction": {
                            "subject": subject,
                            "mood": [mood],
                            "style": [style],
                            "palette": [palette],
                            "composition": composition,
                            "medium": medium,
                            "era": era,
                        }
                    }
                ],
            }
        )
    return examples


def split_examples() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    examples = build_examples()
    evaluation = [example for index, example in enumerate(examples) if (index // 3) % 6 == 0]
    training = [example for index, example in enumerate(examples) if (index // 3) % 6 != 0]
    return training, evaluation


def write_datasets(output_directory: Path) -> tuple[Path, Path]:
    training, evaluation = split_examples()
    output_directory.mkdir(parents=True, exist_ok=True)
    train_path = output_directory / "glia_visual_direction_train.jsonl"
    eval_path = output_directory / "glia_visual_direction_eval.jsonl"
    train_path.write_text(_as_jsonl(training), encoding="utf-8")
    eval_path.write_text(_as_jsonl(evaluation), encoding="utf-8")
    return train_path, eval_path


def _render_text(
    *,
    index: int,
    subject: str,
    mood: str,
    style: str,
    palette: str,
    composition: str,
    medium: str,
    era: str,
) -> str:
    values = {
        "subject": subject,
        "mood": mood,
        "style": style,
        "palette": palette,
        "composition": composition,
        "medium": medium,
        "era": era,
    }
    templates = [
        (
            "Vull representar {subject} en format {medium}, amb un ambient {mood}, "
            "estil {style}, paleta {palette}, {composition} i referències de {era}."
        ),
        (
            "Quiero representar {subject} en formato {medium}, con un tono {mood}, "
            "estilo {style}, colores {palette}, {composition} y referencias de {era}."
        ),
        (
            "Create {subject} using {medium}: {mood} mood, {style} style, {palette} palette, "
            "{composition}, set in {era}."
        ),
    ]
    return templates[index % len(templates)].format(**values)


def _as_jsonl(examples: list[dict[str, object]]) -> str:
    return "".join(_serialized_lines(examples))


def _serialized_lines(examples: list[dict[str, object]]) -> Iterator[str]:
    for example in examples:
        yield json.dumps(example, ensure_ascii=False, separators=(",", ":")) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Glia's Pioneer fine-tuning datasets")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("training"),
        help="Directory for train and evaluation JSONL files",
    )
    args = parser.parse_args()
    train_path, eval_path = write_datasets(args.output)
    print(f"Wrote {TRAIN_SIZE} training rows to {train_path}")
    print(f"Wrote {EVAL_SIZE} evaluation rows to {eval_path}")


if __name__ == "__main__":
    main()
