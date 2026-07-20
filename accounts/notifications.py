"""Email notifications for faculty (CRC revision requests, etc.)."""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)


def _dashboard_login_url(request=None):
    path = reverse("login")
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def notify_faculty_by_email(*, faculty, subject, body):
    """
    Send an email to a faculty member. Returns True if sent.
    Never raises — revision flows should succeed even if mail fails.
    """
    if not faculty or not getattr(faculty, "email", None):
        logger.warning(
            "Skipping revision notification: faculty has no email (user_id=%s)",
            getattr(faculty, "id", None),
        )
        return False

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[faculty.email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception(
            "Failed to send revision notification to %s",
            faculty.email,
        )
        return False


def notify_faculty_outline_revision(*, outline, notes="", request=None, requested_by=None):
    """Notify the outline author that CRC requested a revision."""
    faculty = outline.faculty
    course = outline.course
    if requested_by:
        requester = requested_by.get_full_name() or requested_by.username
    else:
        requester = "CRC"
    notes_block = (notes or outline.notes or "").strip() or "(No notes provided.)"
    login_url = _dashboard_login_url(request)

    subject = f"ACQIP: Revision requested — Course Outline ({course.code})"
    body = (
        f"Hello {faculty.get_full_name() or faculty.username},\n\n"
        f"The Curriculum Review Committee ({requester}) has requested a revision "
        f"for your course outline.\n\n"
        f"Course: {course.code} — {course.title}\n"
        f"Outline: {outline.title} (version {outline.version})\n\n"
        f"CRC feedback:\n{notes_block}\n\n"
        f"Please sign in to ACQIP, update the outline, and resubmit.\n"
        f"{login_url}\n\n"
        f"— ACQIP System\n"
        f"Capital University of Science and Technology\n"
    )
    return notify_faculty_by_email(faculty=faculty, subject=subject, body=body)


def notify_faculty_form_revision(*, submission, notes="", request=None, requested_by=None):
    """Notify the submitting faculty that CRC requested a form revision."""
    faculty = submission.faculty
    course = submission.course
    form = submission.dynamic_form
    if requested_by:
        requester = requested_by.get_full_name() or requested_by.username
    else:
        requester = "CRC"
    notes_block = (notes or "").strip() or "(No notes provided.)"
    login_url = _dashboard_login_url(request)

    subject = (
        f"ACQIP: Revision requested — {form.name} ({course.code})"
    )
    body = (
        f"Hello {faculty.get_full_name() or faculty.username},\n\n"
        f"The Curriculum Review Committee ({requester}) has requested a revision "
        f"for your form submission.\n\n"
        f"Form: {form.name}\n"
        f"Course: {course.code} — {course.title}\n"
        f"Section: {submission.section or 'N/A'}\n\n"
        f"CRC feedback:\n{notes_block}\n\n"
        f"Please sign in to ACQIP, revise your answers, and resubmit.\n"
        f"{login_url}\n\n"
        f"— ACQIP System\n"
        f"Capital University of Science and Technology\n"
    )
    return notify_faculty_by_email(faculty=faculty, subject=subject, body=body)
