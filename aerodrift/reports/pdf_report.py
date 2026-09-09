"""PDF incident report generator.

Filled in during Week 4. Summarizes what drifted and how it was fixed.
"""


def generate_incident_report(drift: dict, remediation_code: str, output_path: str) -> None:
    """Generate a PDF incident report.

    Args:
        drift: the drift object that was detected.
        remediation_code: the code generated and executed to fix it.
        output_path: where to write the PDF.
    """
    raise NotImplementedError("pdf_report: implemented in Week 4")
