"""Tool registry and navigation structure. Tool pages are imported lazily (fast startup)."""
from __future__ import annotations

if __package__ in (None, ''):
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import main as _main_bootstrap  # noqa: F401

import importlib
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDef:
    id: str
    title: str
    desc: str
    category: str
    icon: str
    module: str
    cls: str

    def create(self, settings):
        return getattr(importlib.import_module(self.module), self.cls)(settings)


TOOLS: list[ToolDef] = [
    # Organize PDF
    ToolDef("merge", "Merge PDF", "Combine several PDFs into one", "organize", "merge", "ui.merge_page", "MergePage"),
    ToolDef("split", "Split PDF", "Split by page, range or every N pages", "organize", "split", "ui.split_page", "SplitPage"),
    ToolDef("organize", "Organize PDF", "Reorder, rotate, duplicate and delete pages", "organize", "organize", "ui.organize_page", "OrganizePage"),
    ToolDef("remove", "Remove Pages", "Delete selected pages from a PDF", "organize", "remove", "ui.pages_page", "RemovePagesPage"),
    ToolDef("extract", "Extract Pages", "Export chosen pages as a new PDF", "organize", "extract", "ui.pages_page", "ExtractPagesPage"),
    ToolDef("rotate", "Rotate PDF", "Rotate all or selected pages", "organize", "rotate", "ui.pages_page", "RotatePdfPage"),
    ToolDef("remove_blank", "Remove Blank Pages", "Automatically detect and delete empty pages", "organize", "remove_blank", "ui.utilities_page", "RemoveBlankPagesPage"),
    ToolDef("compare", "Compare PDFs", "Compare two PDFs side-by-side (text & visual diff)", "organize", "compare", "ui.utilities_page", "ComparePdfsPage"),
    ToolDef("batch_rename", "Batch Rename", "Rename multiple PDFs with numbering & patterns", "organize", "batch_rename", "ui.utilities_page", "BatchRenamePage"),
    # Convert PDF (Phase 1 + Phase 3 Office & Extraction)
    ToolDef("pdf2img", "PDF to Image", "Export pages as JPG, PNG or TIFF", "convert", "pdf2img", "ui.convert_page", "PdfToImagePage"),
    ToolDef("img2pdf", "Image to PDF", "Turn JPG, PNG, BMP, TIFF into a PDF", "convert", "img2pdf", "ui.convert_page", "ImageToPdfPage"),
    ToolDef("pdf2docx", "PDF to Word", "Convert PDF into an editable .docx document", "convert", "word", "ui.convert_page", "PdfToWordPage"),
    ToolDef("pdf2xlsx", "PDF to Excel", "Extract PDF tables into an .xlsx workbook", "convert", "excel", "ui.convert_page", "PdfToExcelPage"),
    ToolDef("pdf2pptx", "PDF to PowerPoint", "Turn PDF pages into .pptx slides", "convert", "ppt", "ui.convert_page", "PdfToPptxPage"),
    ToolDef("office2pdf", "Office to PDF", "Convert Word, Excel or PowerPoint to PDF", "convert", "office2pdf", "ui.convert_page", "OfficeToPdfPage"),
    ToolDef("extract_text", "Extract Text", "Export selectable text to a UTF-8 .txt file", "convert", "extract_text", "ui.utilities_page", "ExtractTextPage"),
    ToolDef("extract_images", "Extract Images", "Save all embedded images from a PDF", "convert", "extract_images", "ui.utilities_page", "ExtractImagesPage"),
    # Compress & Optimize PDF
    ToolDef("compress", "Compress PDF", "Make PDF files smaller while keeping text sharp", "compress", "compress", "ui.compress_page", "CompressPage"),
    ToolDef("repair", "Repair PDF", "Recover pages from damaged or corrupted PDFs", "compress", "repair", "ui.utilities_page", "RepairPdfPage"),
    ToolDef("grayscale", "Grayscale PDF", "Convert color PDFs to black-and-white / grayscale", "compress", "grayscale", "ui.utilities_page", "GrayscalePdfPage"),
    ToolDef("flatten", "Flatten PDF", "Merge annotations and form fields into page content", "compress", "flatten", "ui.utilities_page", "FlattenPdfPage"),
    # Edit PDF (Phase 2)
    ToolDef("annotate", "Edit & Annotate", "Add text, images, highlights, underlines, shapes & ink", "edit", "edit", "ui.edit_page", "AnnotatePage"),
    ToolDef("page_numbers", "Page Numbers", "Add customizable page numbers to any corner or margin", "edit", "page_numbers", "ui.edit_page", "PageNumbersPage"),
    ToolDef("header_footer", "Headers & Footers", "Add left, center or right headers and footers", "edit", "header_footer", "ui.edit_page", "HeaderFooterPage"),
    ToolDef("watermark", "Watermark PDF", "Stamp text or image watermarks with opacity & angle", "edit", "watermark", "ui.edit_page", "WatermarkPage"),
    ToolDef("crop", "Crop Pages", "Trim top, bottom, left and right page margins", "edit", "crop", "ui.edit_page", "CropPage"),
    ToolDef("metadata", "Edit Metadata", "View, edit or strip PDF document properties", "edit", "metadata", "ui.edit_page", "MetadataPage"),
    # PDF Security (Phase 2)
    ToolDef("protect", "Protect PDF", "Encrypt with AES-256 password and set permissions", "security", "protect", "ui.security_page", "ProtectPage"),
    ToolDef("unlock", "Unlock PDF", "Remove password protection with authorized credentials", "security", "unlock", "ui.security_page", "UnlockPage"),
    ToolDef("redact", "Redact PDF", "Permanently destroy sensitive text & pixels (verified)", "security", "redact", "ui.security_page", "RedactPage"),
    ToolDef("sign", "Sign PDF", "Apply a signature stamp, SHA-256 digest & optional lock", "security", "sign", "ui.security_page", "SignPage"),
    # OCR Tools (Phase 3)
    ToolDef("ocr", "OCR PDF", "Recognize scanned documents (searchable PDF or text)", "ocr", "ocr", "ui.ocr_page", "OcrPage"),
    # Reader
    ToolDef("reader", "PDF Reader", "View, search and print PDF files", "read", "reader", "ui.viewer_page", "ViewerPage"),
]
TOOL_BY_ID = {t.id: t for t in TOOLS}

CATEGORY_TITLES = {
    "organize": "Organize PDF",
    "convert": "Convert PDF",
    "compress": "Compress & Optimize PDF",
    "edit": "Edit PDF",
    "security": "PDF Security",
    "ocr": "OCR Tools",
    "read": "View PDF",
}

# (key, label, icon) - order of the left sidebar
SIDEBAR: list[tuple[str, str, str]] = [
    ("dashboard", "Dashboard", "dashboard"),
    ("cat:organize", "Organize PDF", "organize"),
    ("cat:convert", "Convert PDF", "pdf2img"),
    ("cat:compress", "Compress PDF", "compress"),
    ("cat:edit", "Edit PDF", "edit"),
    ("cat:security", "PDF Security", "security"),
    ("cat:ocr", "OCR Tools", "ocr"),
    ("recent", "Recent Files", "recent"),
    ("settings", "Settings", "settings"),
    ("about", "About", "about"),
]

UPCOMING: dict[str, tuple[str, str, list[str]]] = {}


if __name__ == '__main__':
    from main import main as _run_main

    raise SystemExit(_run_main())
