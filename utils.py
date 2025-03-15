import os

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from pypdf import PdfWriter
import datetime


DATA_FORMAT = "%d.%m.%Y %H:%M:%S"


def datetime_to_text(dt: datetime):
    return dt.strftime(DATA_FORMAT)


def datetime_now():
    """
    return current UTC time without timezone, not microseconds
    :return:
    """
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).replace(microsecond=0)


def create_pdf(filename, text):
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter

    lines = text.split("\n")
    y_position = height - 40

    for line in lines:
        line = line.replace("\t", "    ")

        c.drawString(40, y_position, line)
        y_position -= 14

        if y_position < 40:
            c.showPage()
            y_position = height - 40

    c.save()


def merge_pdfs(files, result_file):
    merger = PdfWriter()
    for pdf in files:
        merger.append(pdf)
    merger.write(result_file)
    merger.close()
    for file in files:
        os.remove(file)
