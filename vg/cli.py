from __future__ import annotations

import argparse
from pathlib import Path

from .init_project import init_project
from .images import fetch_images
from .import_url import import_url
from .import_file import import_file
from .dialog import build_dialog_segments
from .speakers import assign_speakers
from .render import render_long
from .script import build_script_segments
from .shorts import render_shorts
from .timeline import build_timeline
from .tts import synthesize_tts
from .visuals import assign_visuals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vg", description="半自動の動画生成ツール（MVP）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="新しい案件ディレクトリを作成")
    p_init.add_argument("slug", type=str)

    p_script = sub.add_parser("script", help="記事から読み上げセグメントを生成")
    p_script.add_argument("project_dir", type=Path)
    p_script.add_argument("--source", default="source/article.md")

    p_tts = sub.add_parser("tts", help="VOICEVOX(VOICEBOX)で音声生成")
    p_tts.add_argument("project_dir", type=Path)
    p_tts.add_argument("--base-url", default=None, help="例: http://localhost:50021 (project.jsonを上書き)")
    p_tts.add_argument("--speaker", default=None, type=int, help="speaker id (project.jsonを上書き)")
    p_tts.add_argument("--force", action="store_true", help="既存wavがあっても再生成")

    p_timeline = sub.add_parser("timeline", help="音声尺からタイムライン(開始/終了)を作成")
    p_timeline.add_argument("project_dir", type=Path)
    p_timeline.add_argument("--concat-wav", action="store_true", help="master.wav も生成")

    p_render = sub.add_parser("render", help="長尺マスター動画(仮)を書き出し")
    p_render.add_argument("project_dir", type=Path)
    p_render.add_argument("--out", default=None, help="出力mp4 (デフォルト: export/master_long.mp4)")
    p_render.add_argument("--fontfile", default=None, help="drawtext用フォントファイルへのパス（任意）")
    p_render.add_argument("--force", action="store_true", help="中間生成物があっても再生成")

    p_shorts = sub.add_parser("shorts", help="Shorts(9:16)を書き出し")
    p_shorts.add_argument("project_dir", type=Path)
    p_shorts.add_argument("--in", dest="in_path", default=None, help="入力長尺mp4 (デフォルト: export/master_long.mp4)")
    p_shorts.add_argument("--out-dir", default=None, help="出力ディレクトリ (デフォルト: export/shorts)")
    p_shorts.add_argument("--id", dest="one_id", default=None, help="1本だけ作る場合のid（任意）")
    p_shorts.add_argument("--title", default=None, help="1本だけ作る場合のタイトル（任意）")
    p_shorts.add_argument("--start", default=None, type=float, help="秒指定 start")
    p_shorts.add_argument("--end", default=None, type=float, help="秒指定 end")
    p_shorts.add_argument("--segments", default=None, help="セグメントIDをカンマ区切りで指定 (例: 0002_イントロ,0003_本編)")
    p_shorts.add_argument("--fontfile", default=None, help="drawtext用フォントファイルへのパス（任意）")
    p_shorts.add_argument("--force", action="store_true", help="既存mp4があっても再生成")

    p_imgs = sub.add_parser("fetch-images", help="Markdown内の画像URLをダウンロード")
    p_imgs.add_argument("project_dir", type=Path)
    p_imgs.add_argument("--md", default="source/article.md", help="対象Markdown (project_dirからの相対パス)")
    p_imgs.add_argument("--out-dir", default="assets/images/article", help="出力先ディレクトリ (project_dirからの相対パス)")
    p_imgs.add_argument("--rewrite", action="store_true", help="Markdownをローカルパス参照に書き換え")

    p_import = sub.add_parser("import-url", help="URLから記事を取得して案件を作成")
    p_import.add_argument("url", type=str)
    p_import.add_argument("--slug", default=None, help="案件slug（省略時はURL/タイトルから推測）")
    p_import.add_argument("--force", action="store_true", help="既存 article.md があっても上書き")
    p_import.add_argument("--fetch-images", action="store_true", help="記事内画像をダウンロード（assets/images/article）")
    p_import.add_argument("--rewrite-images", action="store_true", help="Markdownの画像URLをローカル参照に書き換え")

    p_import_file = sub.add_parser("import-file", help="txt/docx/pptx/md から記事Markdownを作って案件を作成")
    p_import_file.add_argument("path", type=Path)
    p_import_file.add_argument("--slug", default=None, help="案件slug（省略時はファイル名から推測）")
    p_import_file.add_argument("--title", default=None, help="記事タイトル（省略時はslug）")
    p_import_file.add_argument("--force", action="store_true", help="既存 article.md があっても上書き")
    p_import_file.add_argument("--no-extract-images", action="store_true", help="docx/pptx から画像を抽出しない")

    p_dialog = sub.add_parser("dialog", help="対話台本(dialog.md)から segments.json を生成")
    p_dialog.add_argument("project_dir", type=Path)
    p_dialog.add_argument("--source", default="script/dialog.md", help="対話台本 (project_dirからの相対パス)")
    p_dialog.add_argument("--force", action="store_true", help="既存 segments/*.txt を削除して再生成")

    p_assign = sub.add_parser("assign-speakers", help="segments.json に speaker id を割り当て")
    p_assign.add_argument("project_dir", type=Path)
    p_assign.add_argument("--speakers", required=True, help="speaker id をカンマ区切り (例: 1,8)")
    p_assign.add_argument("--mode", default="alternate", choices=["alternate"])
    p_assign.add_argument("--all", action="store_true", help="既に speaker があるセグメントも上書き")

    p_visuals = sub.add_parser("visuals", help="各セグメントの表示画像を割り当て（画像が無い箇所のみスライド生成）")
    p_visuals.add_argument("project_dir", type=Path)
    p_visuals.add_argument("--force", action="store_true", help="既存の assets/images/{seg_id} を上書き")

    args = parser.parse_args(argv)

    if args.cmd == "init":
        init_project(args.slug)
        return 0
    if args.cmd == "script":
        build_script_segments(args.project_dir, source_relpath=args.source)
        return 0
    if args.cmd == "tts":
        synthesize_tts(
            args.project_dir,
            base_url=args.base_url,
            speaker=args.speaker,
            force=args.force,
        )
        return 0
    if args.cmd == "timeline":
        build_timeline(args.project_dir, concat_wav=args.concat_wav)
        return 0
    if args.cmd == "render":
        render_long(args.project_dir, out=args.out, fontfile=args.fontfile, force=args.force)
        return 0
    if args.cmd == "shorts":
        render_shorts(
            args.project_dir,
            in_path=args.in_path,
            out_dir=args.out_dir,
            one_id=args.one_id,
            title=args.title,
            start=args.start,
            end=args.end,
            segments=args.segments,
            fontfile=args.fontfile,
            force=args.force,
        )
        return 0
    if args.cmd == "fetch-images":
        fetch_images(args.project_dir, md_relpath=args.md, out_relpath=args.out_dir, rewrite=args.rewrite)
        return 0
    if args.cmd == "import-url":
        import_url(
            args.url,
            slug=args.slug,
            force=args.force,
            fetch_article_images=args.fetch_images,
            rewrite_images=args.rewrite_images,
        )
        return 0
    if args.cmd == "import-file":
        import_file(
            args.path,
            slug=args.slug,
            title=args.title,
            force=args.force,
            extract_images=not args.no_extract_images,
        )
        return 0
    if args.cmd == "dialog":
        build_dialog_segments(args.project_dir, source_relpath=args.source, force=args.force)
        return 0
    if args.cmd == "assign-speakers":
        speaker_ids = [int(x.strip()) for x in args.speakers.split(",") if x.strip()]
        assign_speakers(
            args.project_dir,
            speakers=speaker_ids,
            mode=args.mode,
            only_missing=not args.all,
        )
        return 0
    if args.cmd == "visuals":
        assign_visuals(args.project_dir, force=args.force)
        return 0

    parser.error("unknown command")
    return 2
