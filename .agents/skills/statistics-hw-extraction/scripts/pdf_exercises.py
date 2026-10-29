#!/usr/bin/env python3
"""Locate PDF exercises and execute visually reviewed, dependency-aware crops."""

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile

try:
    import pypdfium2 as pdfium
    from PIL import Image
except ImportError as error:
    raise SystemExit('Missing dependency. Use an environment with requirements.txt installed.') from error


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def exercise_ids(value, label, allow_empty=False):
    require(isinstance(value, list) and (allow_empty or bool(value)), f'{label}: expected a list of exercise IDs')
    require(all(isinstance(x, (str, int)) and not isinstance(x, bool) and str(x).strip() for x in value), f'{label}: invalid exercise ID')
    result = [str(x).strip() for x in value]
    require(len(set(result)) == len(result), f'{label}: duplicate exercise ID')
    return result


def validate_source_catalog(plan, used_ids):
    """Disambiguate repeated exercise numbers across sections and source kinds."""
    catalog = plan.get('source_catalog')
    qualified = any(':' in item for item in used_ids)
    if catalog is None and not qualified:
        return  # Older single-section plans remain replayable.
    require(isinstance(catalog, dict), 'Qualified source IDs require a source_catalog')
    require(set(used_ids) <= set(catalog), 'source_catalog is missing a referenced source ID')
    for source_id in used_ids:
        entry = catalog[source_id]
        require(isinstance(entry, dict), f'Invalid source_catalog entry: {source_id}')
        kind = entry.get('kind', 'exercise')
        require(kind in ('exercise', 'figure', 'table', 'example', 'text'), f'Unknown source kind: {kind}')
        value = entry.get('number')
        require(isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip(), 'Catalog source needs a number or stable text identifier')
        if kind == 'exercise':
            section = entry.get('section')
            require(isinstance(section, str) and section.strip(), f'Exercise {source_id} needs its section')
            expected_id = f'{section.strip().upper()}:{str(value).strip()}'
        else:
            expected_id = f'{kind}:{str(value).strip()}'
        require(source_id == expected_id, f'Source ID must identify its section or kind: expected {expected_id}')
    for item in exercise_ids(plan.get('requested_exercises'), 'requested_exercises'):
        require(catalog[item].get('kind', 'exercise') == 'exercise', 'Requested assignments must be exercises')


def page_numbers(spec, count):
    selected = set()
    for token in spec.split(','):
        ends = token.strip().split('-')
        require(len(ends) <= 2 and all(x.isdigit() for x in ends), 'Pages must look like 1125-1126,1130')
        start, end = int(ends[0]), int(ends[-1])
        require(1 <= start <= end <= count, f'Page range outside PDF: {token}')
        selected.update(range(start, end + 1))
    return sorted(selected)


def page_text(doc, page_number):
    page = doc[page_number - 1]
    tp = page.get_textpage()
    try:
        return tp.get_text_range()
    finally:
        tp.close()
        page.close()


def source_identity(path, page_count, include_hash=False):
    result = {'size_bytes': path.stat().st_size, 'page_count': page_count}
    if include_hash:
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        result['sha256'] = digest.hexdigest()
    return result


def validate_plan(plan, dimensions):
    """Check semantics declared in a plan; this does not infer missing content."""
    requested = exercise_ids(plan.get('requested_exercises'), 'requested_exercises')
    scale = plan.get('scale', 8)
    require(number(scale) and 1 <= scale <= 8, 'scale must be between 1 and 8')
    groups = plan.get('groups')
    require(isinstance(groups, list) and groups, 'groups must be nonempty')
    raw_deps = plan.get('dependencies', {})
    require(isinstance(raw_deps, dict), 'dependencies must be an object')
    deps = {str(k): exercise_ids(v, f'dependencies[{k}]', allow_empty=True) for k, v in raw_deps.items()}
    used_ids = set(requested) | set(deps)
    for prerequisites in deps.values():
        used_ids.update(prerequisites)
    for group in groups:
        require(isinstance(group, dict), 'Each group must be an object')
        used_ids.update(exercise_ids(group.get('exercises'), 'group.exercises'))
        used_ids.update(exercise_ids(group.get('context_exercises', []), 'context_exercises', allow_empty=True))
    validate_source_catalog(plan, used_ids)

    def visit(node, active, done):
        require(node not in active, f'Cyclic exercise dependency involving {node}')
        if node not in done:
            active.add(node)
            for child in deps.get(node, []):
                visit(child, active, done)
            active.remove(node)
            done.add(node)

    done = set()
    for node in deps:
        visit(node, set(), done)

    seen_exercises, filenames = [], set()
    for group in groups:
        require(isinstance(group, dict), 'Each group must be an object')
        filename = group.get('filename', '')
        require(isinstance(filename, str) and filename and Path(filename).name == filename and '/' not in filename and '\\' not in filename and filename.lower().endswith('.png'), 'Output filename must be a single PNG filename')
        require(filename.casefold() not in filenames, f'Duplicate output filename: {filename}')
        filenames.add(filename.casefold())
        assigned = exercise_ids(group.get('exercises'), 'group.exercises')
        context = exercise_ids(group.get('context_exercises', []), 'context_exercises', allow_empty=True)
        require(set(assigned) <= set(requested), 'Unrequested exercises must be identified as context')
        require(not set(context) & set(requested), 'A selected prerequisite must be grouped as an assigned exercise')
        available = set(assigned + context)
        needed = set()

        def collect_needed(node):
            for prerequisite in deps.get(node, []):
                if prerequisite not in needed:
                    needed.add(prerequisite)
                    collect_needed(prerequisite)

        for exercise in assigned:
            collect_needed(exercise)
        require(set(context) <= needed, 'Context source is unrelated to the requested exercises')
        parts = group.get('parts')
        require(isinstance(parts, list) and parts, 'Each group needs source parts')
        width = None
        pixels = 0
        positions, main_parts = {}, set()
        for index, part in enumerate(parts):
            require(isinstance(part, dict), 'Each part must be an object')
            exercise = str(part.get('exercise', ''))
            require(exercise in available, f'Part exercise {exercise} not in its group')
            role = part.get('role', 'exercise')
            require(role in ('exercise', 'context'), 'Part role must be exercise or context')
            require(exercise not in context or role == 'context', 'Unassigned prerequisite parts must have role context')
            if role == 'context' and (':' in exercise or 'supports' in part):
                supports = exercise_ids(part.get('supports'), 'context part supports')
                require(set(supports) <= available, 'Context supports a source outside its group')
                require(all((exercise == item and exercise in assigned) or exercise in deps.get(item, []) for item in supports), 'Context supports must match the declared dependencies')
                require(isinstance(part.get('reason'), str) and part['reason'].strip(), 'Context part needs a reason describing the necessary information')
            if role == 'exercise':
                main_parts.add(exercise)
            positions.setdefault(exercise, []).append(index)
            page = part.get('page')
            require(isinstance(page, int) and not isinstance(page, bool) and page in dimensions, f'Invalid PDF page: {page}')
            box = part.get('box')
            require(isinstance(box, list) and len(box) == 4 and all(number(v) for v in box), 'box must contain four finite coordinates')
            left, top, right, bottom = box
            page_width, page_height = dimensions[page]
            require(0 <= left < right <= page_width and 0 <= top < bottom <= page_height, f'Crop outside PDF page {page}: {box}')
            pixel_width = round(right * scale) - round(left * scale)
            pixel_height = round(bottom * scale) - round(top * scale)
            require(pixel_width > 0 and pixel_height > 0, 'Crop rounds to an empty image')
            if width is None:
                width = pixel_width
            require(pixel_width == width, 'All regions in one group must have the same rendered width')
            gap = part.get('gap_after_points', 0)
            require(number(gap) and 0 <= gap <= 144, 'gap_after_points must be between 0 and 144')
            if gap:
                rgb = group.get('background_rgb')
                require(isinstance(rgb, list) and len(rgb) == 3 and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in rgb), 'Added gaps require an explicit background_rgb')
            pixels += width * (pixel_height + round(gap * scale))
        require(pixels <= 100_000_000, 'Output exceeds 100 million pixels; review grouping or scale')
        require(set(assigned) <= main_parts, 'An assigned exercise has no exercise part')
        require(available <= set(positions), 'A context exercise has no source part')
        for exercise in available:
            for prerequisite in deps.get(exercise, []):
                require(prerequisite in available, f'Exercise {exercise} requires {prerequisite} in the same group')
                require(max(positions[prerequisite]) < min(positions[exercise]), f'Prerequisite {prerequisite} must precede exercise {exercise}')
        seen_exercises.extend(assigned)
    require(Counter(seen_exercises) == Counter(requested), 'Each requested exercise must occur in exactly one output group')


def render_crop(doc, page_number, scale, box=None):
    page = doc[page_number - 1]
    bitmap = None
    try:
        width, height = page.get_size()
        require(math.ceil(width * scale) * math.ceil(height * scale) <= 100_000_000, 'Rendered source page exceeds 100 million pixels; reduce scale')
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil().convert('RGB').copy()
        if box is not None:
            image = image.crop(tuple(round(v * scale) for v in box))
        return image
    finally:
        if bitmap is not None:
            bitmap.close()
        page.close()


def extract(args):
    plan_path = Path(args.plan).expanduser().resolve()
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    require(isinstance(plan, dict), 'Plan must be a JSON object')
    source = Path(args.pdf).expanduser().resolve() if args.pdf else (plan_path.parent / plan['source_pdf']).expanduser().resolve()
    require(source.is_file(), f'PDF not found: {source}')
    doc = pdfium.PdfDocument(str(source))
    try:
        expected = plan.get('source_identity', {})
        require(isinstance(expected, dict), 'source_identity must be an object')
        identity = source_identity(source, len(doc), include_hash='sha256' in expected)
        for key in ('size_bytes', 'page_count', 'sha256'):
            if key in expected:
                require(identity[key] == expected[key], f'Source PDF {key} mismatch; recheck the plan against the actual edition')
        # Supply dimensions for referenced pages only, without parsing all pages.
        dimensions = {}
        for group in plan.get('groups', []):
            if not isinstance(group, dict):
                continue
            for part in group.get('parts', []):
                if not isinstance(part, dict):
                    continue
                n = part.get('page')
                if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(doc) and n not in dimensions:
                    page = doc[n - 1]
                    dimensions[n] = page.get_size()
                    page.close()
        validate_plan(plan, dimensions)
        out = Path(args.out).expanduser().resolve()
        destinations = [out / g['filename'] for g in plan['groups']] + [out / 'manifest.json']
        require(args.overwrite or not any(p.exists() for p in destinations), 'Output already exists; use a new directory or explicitly pass --overwrite')
        require(source not in [p.resolve() for p in destinations], 'Output cannot overwrite the source PDF')
        out.mkdir(parents=True, exist_ok=True)
        scale = plan.get('scale', 8)
        outputs = []
        # Prepare every image before replacing destination files.
        with tempfile.TemporaryDirectory(prefix='.extract-', dir=out) as scratch:
            staging = Path(scratch)
            for group in plan['groups']:
                pieces = [render_crop(doc, p['page'], scale, p['box']) for p in group['parts']]
                height = sum(im.height + round(p.get('gap_after_points', 0) * scale) for im, p in zip(pieces, group['parts']))
                merged = Image.new('RGB', (pieces[0].width, height), tuple(group.get('background_rgb', [255, 255, 255])))
                offset, joins = 0, []
                for piece, part in zip(pieces, group['parts']):
                    merged.paste(piece, (0, offset))
                    require(merged.crop((0, offset, piece.width, offset + piece.height)).tobytes() == piece.tobytes(), 'Unexpected change to source pixels')
                    offset += piece.height + round(part.get('gap_after_points', 0) * scale)
                    joins.append(offset)
                path = staging / group['filename']
                merged.save(path, dpi=(72 * scale, 72 * scale))
                with Image.open(path) as saved:
                    saved.load()
                    require(saved.size == merged.size, 'Saved image has unexpected dimensions')
                outputs.append({'filename': group['filename'], 'exercises': group['exercises'], 'width': merged.width, 'height': merged.height, 'join_rows': joins[:-1]})
            manifest = {'source_pdf': str(source), 'source_identity': identity, 'plan': plan, 'outputs': outputs, 'review': 'Visual verification of every PNG is required before delivery.'}
            (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            for destination in destinations:
                os.replace(staging / destination.name, destination)
        emit({'output_dir': str(out), 'outputs': outputs, 'visual_review_required': True})
    finally:
        doc.close()


def inspect_pdf(args):
    source = Path(args.pdf).expanduser().resolve()
    doc = pdfium.PdfDocument(str(source))
    try:
        if args.command == 'info':
            page = doc[0]
            size = page.get_size()
            page.close()
            emit({'source_pdf': str(source), **source_identity(source, len(doc)), 'first_page_size_points': size})
        elif args.command == 'search':
            query = ' '.join(args.query.split()).casefold()
            require(bool(query), 'Search query must not be empty')
            last = args.end_page if args.end_page is not None else len(doc)
            require(1 <= args.start_page <= last <= len(doc), 'Search page range outside PDF')
            require(args.limit >= 1, 'limit must be positive')
            matches = []
            for n in range(args.start_page, last + 1):
                text = ' '.join(page_text(doc, n).split())
                position = text.casefold().find(query)
                if position >= 0:
                    matches.append({'page': n, 'snippet': text[max(0, position - 80):position + len(query) + 240]})
                    if len(matches) >= args.limit:
                        break
            emit({'query': args.query, 'matches': matches})
        elif args.command == 'render':
            require(number(args.scale) and 0.25 <= args.scale <= 8, 'Preview scale must be between 0.25 and 8')
            out = Path(args.out).expanduser().resolve()
            numbers = page_numbers(args.pages, len(doc))
            paths = [out / f'page-{n}.png' for n in numbers]
            require(args.overwrite or not any(p.exists() for p in paths), 'Preview exists; use another directory or --overwrite')
            out.mkdir(parents=True, exist_ok=True)
            for n, path in zip(numbers, paths):
                render_crop(doc, n, args.scale).save(path)
            emit({'preview_images': [str(path) for path in paths]})
        elif args.command == 'lines':
            for n in page_numbers(args.pages, len(doc)):
                page = doc[n - 1]
                tp = page.get_textpage()
                try:
                    height = page.get_height()
                    text, boxes, lines = [], [], []

                    def finish_line():
                        value = ''.join(text).strip()
                        if value and boxes:
                            box = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
                            lines.append({'text': value, 'box': [round(v, 3) for v in box]})
                        text.clear()
                        boxes.clear()

                    for i in range(tp.count_chars()):
                        char = tp.get_text_range(i, 1)
                        if '\r' in char or '\n' in char:
                            finish_line()
                        else:
                            text.append(char)
                            if char.strip():
                                left, bottom, right, top = tp.get_charbox(i)
                                boxes.append((left, height - top, right, height - bottom))
                    finish_line()
                    emit({'page': n, 'size_points': page.get_size(), 'coordinate_origin': 'top-left', 'lines': lines})
                finally:
                    tp.close()
                    page.close()
    finally:
        doc.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('info', 'search', 'render', 'lines'):
        command = commands.add_parser(name)
        command.add_argument('pdf')
        if name in ('render', 'lines'):
            command.add_argument('--pages', required=True, help='One-based file pages, e.g. 1125-1126,1130')
        if name == 'search':
            command.add_argument('--query', required=True)
            command.add_argument('--start-page', type=int, default=1)
            command.add_argument('--end-page', type=int)
            command.add_argument('--limit', type=int, default=10)
        if name == 'render':
            command.add_argument('--out', required=True)
            command.add_argument('--scale', type=float, default=1.5)
            command.add_argument('--overwrite', action='store_true')
    command = commands.add_parser('extract')
    command.add_argument('--plan', required=True)
    command.add_argument('--pdf', help='Override source location, not its identity checks')
    command.add_argument('--out', required=True)
    command.add_argument('--overwrite', action='store_true')
    args = parser.parse_args(argv)
    try:
        extract(args) if args.command == 'extract' else inspect_pdf(args)
    except Exception as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
