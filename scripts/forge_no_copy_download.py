import csv
import json
import os
import tempfile
from contextlib import nullcontext

import gradio as gr

import modules.images
import modules.infotext_utils as parameters_copypaste
import modules.ui_common as ui_common
from modules import shared


__version__ = "1.0.0"

EXTENSION_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP_DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "forge-neo-download")
COUNTER_FILE = os.path.join(EXTENSION_ROOT, ".download_counter")

# v5 stored its counter here. Read it once when migrating to this extension.
WEBUI_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(ui_common.__file__)))
LEGACY_COUNTER_FILE = os.path.join(WEBUI_ROOT, ".forge_download_counter")


def _read_int_file(path):
    try:
        with open(path, "r", encoding="utf8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _initial_counter():
    # Continue exactly from the previous v5 core patch when possible.
    legacy = _read_int_file(LEGACY_COUNTER_FILE)
    if legacy is not None:
        return legacy

    number = 0
    candidates = []

    configured = getattr(shared.opts, "outdir_save", None)
    if configured:
        candidates.append(configured)
        if not os.path.isabs(configured):
            candidates.append(os.path.join(WEBUI_ROOT, configured))

    candidates.append(os.path.join(WEBUI_ROOT, "output", "images"))

    for candidate in candidates:
        try:
            if os.path.isdir(candidate):
                number = max(number, modules.images.get_next_sequence_number(candidate, ""))
        except Exception:
            pass

    return number


def _reserve_download_number():
    number = _read_int_file(COUNTER_FILE)
    if number is None:
        number = _initial_counter()

    try:
        with open(COUNTER_FILE, "w", encoding="utf8") as f:
            f.write(str(number + 1))
    except OSError:
        pass

    return number


def _clean_old_temp_files(keep_paths):
    keep = {os.path.abspath(p) for p in keep_paths if p}
    try:
        names = os.listdir(TEMP_DOWNLOAD_DIR)
    except OSError:
        return

    for name in names:
        path = os.path.join(TEMP_DOWNLOAD_DIR, name)
        if not os.path.isfile(path):
            continue
        if os.path.abspath(path) in keep:
            continue
        try:
            os.remove(path)
        except OSError:
            # Browser/Gradio may still have the previous file open.
            pass


def save_files_no_copy(js_data, images, do_make_zip, index):
    """
    Replacement for modules.ui_common.save_files.

    It preserves Forge's diskette/ZIP behavior but writes the browser-download
    file to the OS temp directory instead of permanently duplicating it in
    output/images. A tiny persistent counter keeps 00000, 00001, 00002...
    numbering independent of temp cleanup.
    """
    filenames = []
    fullfns = []
    parsed_infotexts = []

    class MyObject:
        def __init__(self, d=None):
            if d is not None:
                for key, value in d.items():
                    setattr(self, key, value)

    data = json.loads(js_data)
    p = MyObject(data)

    path = TEMP_DOWNLOAD_DIR
    save_to_dirs = False
    extension = shared.opts.samples_format
    start_index = 0

    if index > -1 and shared.opts.save_selected_only and (index >= data["index_of_first_image"]):
        images = [images[index]]
        start_index = index

    os.makedirs(path, exist_ok=True)

    fields = [
        "prompt",
        "seed",
        "width",
        "height",
        "sampler",
        "cfgs",
        "steps",
        "filename",
        "negative_prompt",
        "sd_model_name",
        "sd_model_hash",
    ]

    logfile_path = os.path.join(path, "log.csv")

    if shared.opts.save_write_log_csv and os.path.exists(logfile_path):
        ui_common.update_logfile(logfile_path, fields)

    context = open(logfile_path, "a", encoding="utf8", newline="") if shared.opts.save_write_log_csv else nullcontext()

    with context as file:
        if file:
            at_start = file.tell() == 0
            writer = csv.writer(file)
            if at_start:
                writer.writerow(fields)

        for image_index, filedata in enumerate(images, start_index):
            image = filedata[0]
            is_grid = image_index < p.index_of_first_image
            p.batch_index = image_index - 1

            try:
                infotext = data["infotexts"][image_index]
                parameters = parameters_copypaste.parse_generation_parameters(infotext, [])
            except (IndexError, KeyError):
                sequence = _reserve_download_number()
                forced_filename = f"{sequence:05}-image"

                fullfn, _ = modules.images.save_image(
                    image,
                    path,
                    "",
                    seed=None,
                    prompt=None,
                    extension=extension,
                    info=None,
                    grid=is_grid,
                    p=p,
                    save_to_dirs=save_to_dirs,
                    forced_filename=forced_filename,
                )

                filename = os.path.relpath(fullfn, path)
                _clean_old_temp_files([fullfn])
                return gr.update(value=[fullfn], visible=True), ui_common.plaintext_to_html(f"Saved: {filename}")

            parsed_infotexts.append(parameters)

            sequence = _reserve_download_number()
            seed = parameters.get("Seed")
            prompt = parameters.get("Prompt")
            seed_for_name = seed if seed is not None else "image"
            forced_filename = f"{sequence:05}-{seed_for_name}"

            fullfn, txt_fullfn = modules.images.save_image(
                image,
                path,
                "",
                seed=seed,
                prompt=prompt,
                extension=extension,
                info=infotext,
                grid=is_grid,
                p=p,
                save_to_dirs=save_to_dirs,
                forced_filename=forced_filename,
            )

            filename = os.path.relpath(fullfn, path)
            filenames.append(filename)
            fullfns.append(fullfn)

            if txt_fullfn:
                filenames.append(os.path.basename(txt_fullfn))
                fullfns.append(txt_fullfn)

        if file and parsed_infotexts:
            first = parsed_infotexts[0]
            writer.writerow([
                first.get("Prompt", ""),
                first.get("Seed", ""),
                data.get("width", ""),
                data.get("height", ""),
                data.get("sampler_name", ""),
                data.get("cfg_scale", ""),
                data.get("steps", ""),
                filenames[0] if filenames else "",
                first.get("Negative prompt", ""),
                data.get("sd_model_name", ""),
                data.get("sd_model_hash", ""),
            ])

    if do_make_zip and fullfns and parsed_infotexts:
        parameters = parsed_infotexts[-1]
        p.all_seeds = [item.get("Seed") for item in parsed_infotexts]

        namegen = modules.images.FilenameGenerator(
            p,
            parsed_infotexts[0].get("Seed"),
            parsed_infotexts[0].get("Prompt"),
            image,
            True,
        )
        zip_filename = namegen.apply(
            shared.opts.grid_zip_filename_pattern or "[datetime]_[[model_name]]_[seed]-[seed_last]"
        )
        zip_filepath = os.path.join(path, f"{zip_filename}.zip")

        from zipfile import ZipFile

        with ZipFile(zip_filepath, "w") as zip_file:
            for i in range(len(fullfns)):
                with open(fullfns[i], mode="rb") as f:
                    zip_file.writestr(filenames[i], f.read())

        fullfns.insert(0, zip_filepath)

    keep = list(fullfns)
    if shared.opts.save_write_log_csv:
        keep.append(logfile_path)
    _clean_old_temp_files(keep)

    shown_name = filenames[0] if filenames else "file"
    return gr.update(value=fullfns, visible=True), ui_common.plaintext_to_html(f"Saved: {shown_name}")


save_files_no_copy._forge_no_copy_download = True


def apply_patch():
    current = getattr(ui_common, "save_files", None)
    if getattr(current, "_forge_no_copy_download", False):
        return

    ui_common.save_files = save_files_no_copy
    print(f"[Forge Neo] forge-no-copy-download v{__version__} loaded")


# Extension scripts are imported before the Forge UI is built, so patch now.
apply_patch()

# Also register a before-UI callback when this Forge build exposes it.
# This makes the patch resilient if another extension reloads ui_common later.
try:
    from modules import script_callbacks
    if hasattr(script_callbacks, "on_before_ui"):
        script_callbacks.on_before_ui(apply_patch)
except Exception:
    pass
