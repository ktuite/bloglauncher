#!/usr/bin/env python3
"""Fetch a Mastodon toot (thread head) and write a Markdown file plus downloaded assets.

Project convention: use `uv` to run scripts (it auto-activates a discovered `.venv`).

Usage examples:
    uv run fetch_toot_thread.py https://mastodon.social/@user/115260608425298248
    uv run fetch_toot_thread.py --instance mastodon.social --id 115260608425298248 --output-dir out
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import html
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from dataclasses import dataclass, field

import requests


@dataclass
class ImageInfo:
    filename: str             # Clean filename for markdown
    alt_text: str            # Alt text for accessibility  
    original_url: str        # For reference/debugging


@dataclass 
class TootSection:
    original_content: str      # Raw toot text for reference
    timestamp: str            # When toot was posted
    images: List[ImageInfo]   # Associated images
    alt_texts: List[str]      # Alt text from images
    section_header: str = "Section"
    narrative_content: str = ""  # Will be filled with actual toot content


@dataclass
class BlogTemplateData:
    # Auto-filled fields
    working_title: str          # First toot content (truncated)
    author_name: str           # Clean author name (without @instance)
    date: str                  # ISO date of first toot
    featured_image: str        # First image filename found in thread
    source_urls: List[str]     # Original toot URLs for attribution
    
    # TODO placeholder fields
    final_title: str = "TODO: REPLACE WITH ACTUAL TITLE"
    description: str = "TODO: Write a compelling description for this post"
    tags: List[str] = field(default_factory=lambda: ['TODO: add tags'])
    
    # Section content
    sections: List[TootSection] = field(default_factory=list)


def fetch_context(instance: str, status_id: str, timeout: int = 10) -> dict:
    api_url = f"https://{instance}/api/v1/statuses/{status_id}/context"
    resp = requests.get(api_url, headers={"Accept": "application/json"}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _parse_created_at(ts: str) -> float:
    """Parse ISO-8601 created_at into POSIX seconds. Return 0.0 on failure."""
    if not ts:
        return 0.0
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        return dt.timestamp()
    except Exception:
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
            return dt.timestamp()
        except Exception:
            return 0.0

def parse_status_url(url: str):
    """Extract (instance_domain, status_id) from a Mastodon status URL.

    Example URL formats handled:
      https://mastodon.social/@user/115260608425298248
      https://mastodon.social/users/user/statuses/115260608425298248
    """
    m = re.search(r"https?://([^/]+)/.*/(\d+)(?:$|[/?#])", url)
    if not m:
        raise ValueError(f"Could not parse status id from URL: {url}")
    domain = m.group(1)
    status_id = m.group(2)
    return domain, status_id


def fetch_status(instance: str, status_id: str, timeout: int = 10) -> dict:
    """Fetch status JSON from instance's API without authentication."""
    api_url = f"https://{instance}/api/v1/statuses/{status_id}"
    resp = requests.get(api_url, headers={"Accept": "application/json"}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def sanitize_filename(name: str) -> str:
    # keep alphanumerics, dash, underscore, dot
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def html_to_markdown_basic(html_text: str) -> str:
    """Very small HTML -> Markdown conversion:
    - convert <a href="...">text</a> to [text](url)
    - remove other tags, unescape entities (fetch_toot.strip_html_tags handles unescape)
    """
    # convert anchor tags
    def repl_a(m):
        href = m.group(1)
        text = re.sub(r"<[^>]+>", "", m.group(2))
        return f"[{text}]({href})"

    text = re.sub(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', repl_a, html_text, flags=re.IGNORECASE | re.DOTALL)
    # remove remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # unescape HTML entities
    text = html.unescape(text)
    # collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_working_title(status: dict) -> str:
    """Extract a working title from the first toot content."""
    content_html = status.get("content", "")
    content_plain = html_to_markdown_basic(content_html)
    
    if not content_plain.strip():
        return "Mastodon Thread"
    
    # Get first line or first 60 characters, whichever is shorter
    first_line = content_plain.strip().splitlines()[0]
    title = first_line[:60].strip()
    
    # Clean up title - remove trailing punctuation that doesn't work well in titles
    title = re.sub(r'[.!?…]+$', '', title)
    
    return title if title else "Mastodon Thread"


def get_clean_author_name(status: dict) -> str:
    """Extract clean author name without @instance suffix."""
    account = status.get("account", {})
    display_name = account.get("display_name", "").strip()
    acct = account.get("acct", "").strip()
    
    # Prefer display name, fall back to account name without instance
    if display_name:
        return display_name
    elif acct:
        # Remove @instance.domain part if present
        return acct.split('@')[0]
    else:
        return "Unknown Author"


def find_featured_image(statuses: List[dict]) -> str:
    """Find the first image in the thread to use as featured image."""
    for status in statuses:
        media = status.get("media_attachments", []) or []
        for idx, m in enumerate(media, start=1):
            remote = m.get("url") or m.get("preview_url")
            if remote:
                status_id = status.get("id")
                orig_name = Path(remote).name
                filename = sanitize_filename(f"{status_id}_{idx}_{orig_name}")
                return filename
    return ""


def download_media(url: str, dest: Path, timeout: int = 20) -> Path:
    resp = requests.get(url, stream=True, timeout=timeout)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)
    return dest


def build_blog_frontmatter(template_data: BlogTemplateData) -> str:
    """Build blog-friendly front matter with TODO placeholders."""
    # Convert ISO timestamp to readable format
    try:
        if template_data.date.endswith("Z"):
            date_str = template_data.date[:-1] + "+00:00"
        else:
            date_str = template_data.date
        dt = datetime.fromisoformat(date_str)
        formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        formatted_date = template_data.date
    
    front = ["---"]
    front.append(f'author: {template_data.author_name}')
    front.append(f'title: "{template_data.final_title}"')
    front.append(f'date: {formatted_date}')
    front.append(f'description: "{template_data.description}"')
    
    if template_data.featured_image:
        front.append(f'image: {template_data.featured_image}')
    
    front.append('draft: false')
    front.append(f'Tags: {template_data.tags}')
    front.append("---\n")
    return "\n".join(front)


def build_frontmatter(first_status: dict, source_urls: str, instance: str, toot_ids: list[str]) -> str:
    created = first_status.get("created_at", "")
    acct = first_status.get("account", {}).get("acct") or first_status.get("account", {}).get("display_name") or "(unknown)"
    content_plain = html_to_markdown_basic(first_status.get("content", ""))
    title = content_plain.strip().splitlines()[0][:60] if content_plain.strip() else "Mastodon Thread"
    summary = content_plain.replace('\n', ' ')[:160] if content_plain else "Combined Mastodon thread"

    front = ["---"]
    front.append(f'title: "{title}"')
    front.append(f'date: "{created}"')
    front.append(f'author: "{acct}@{instance}"')
    front.append(f'source_urls: "{source_urls}"')
    front.append(f'mastodon_instance: "{instance}"')
    front.append('toot_ids:')
    for tid in toot_ids:
        front.append(f'  - {tid}')
    front.append(f'summary: "{summary}"')
    front.append("---\n")
    return "\n".join(front)


def create_image_info_list(status: dict) -> List[ImageInfo]:
    """Create ImageInfo objects for all media in a status."""
    images = []
    media = status.get("media_attachments", []) or []
    status_id = status.get("id")
    
    for idx, m in enumerate(media, start=1):
        remote = m.get("url") or m.get("preview_url")
        if not remote:
            continue
            
        orig_name = Path(remote).name
        filename = sanitize_filename(f"{status_id}_{idx}_{orig_name}")
        
        # Get alt text, clean it up
        desc = m.get("description") or ""
        alt_text = html_to_markdown_basic(desc) if desc else filename
        
        images.append(ImageInfo(
            filename=filename,  # Just the filename, no path
            alt_text=alt_text,
            original_url=remote
        ))
    
    return images


def create_section_template(status: dict) -> str:
    """Create a template section that wraps toot content in comments with TODO guidance."""
    # Extract toot content and metadata
    content_html = status.get("content", "")
    content_plain = html_to_markdown_basic(content_html)
    timestamp = status.get("created_at", "")
    
    # Get images for this toot
    images = create_image_info_list(status)
    
    # Build the comment block with original content
    comment_lines = [
        "<!-- Original toot content:",
        f"{timestamp} - {content_plain}"
    ]
    
    # Add alt text information if images exist
    if images:
        comment_lines.append("")
        comment_lines.append("Alt text for images:")
        for idx, img in enumerate(images, start=1):
            comment_lines.append(f"- Image {idx}: {img.alt_text}")
    
    comment_lines.append("-->")
    
    # Build the template section
    section_parts = [
        "## Section",
        "",
        "\n".join(comment_lines),
        "",
        content_plain,
        ""
    ]
    
    # Add inline images if they exist
    if images:
        image_markdown = format_inline_images(images)
        section_parts.append(image_markdown)
        section_parts.append("")
    
    return "\n".join(section_parts)


def format_inline_images(images: List[ImageInfo]) -> str:
    """Format multiple images in inline style matching example.md."""
    if not images:
        return ""
    
    # Create space-separated inline image markdown
    image_parts = []
    for img in images:
        image_parts.append(f"![{img.alt_text}]({img.filename})")
    
    return " ".join(image_parts)


def create_attribution_footer(source_urls: List[str]) -> str:
    """Create minimal attribution footer for source links."""
    if not source_urls:
        return ""
    footer_parts = [
        "---",
        "",
    ]

    if len(source_urls) == 1:
        footer_parts.append(f"*This post is based on a Mastodon thread. View original: [Thread starting here]({source_urls[0]})*")
    else:
        footer_parts.append("*This post is based on multiple Mastodon threads. View originals:*")
        footer_parts.append("")
        for idx, url in enumerate(source_urls, start=1):
            footer_parts.append(f"{idx}. [Thread starting here]({url})")
    
    return "\n".join(footer_parts)


def build_template_from_statuses(statuses: List[dict], source_urls: List[str]) -> BlogTemplateData:
    """Build complete blog template data from list of statuses."""
    if not statuses:
        raise ValueError("No statuses provided")
    
    first_status = statuses[0]
    
    # Extract basic template data
    template_data = BlogTemplateData(
        working_title=extract_working_title(first_status),
        author_name=get_clean_author_name(first_status),
        date=first_status.get("created_at", ""),
        featured_image=find_featured_image(statuses),
        source_urls=source_urls
    )
    
    # Create sections for each toot
    for status in statuses:
        content_plain = html_to_markdown_basic(status.get("content", ""))
        images = create_image_info_list(status)
        
        section = TootSection(
            original_content=content_plain,
            timestamp=status.get("created_at", ""),
            images=images,
            alt_texts=[img.alt_text for img in images]
        )
        template_data.sections.append(section)
    
    return template_data


def generate_blog_template(template_data: BlogTemplateData) -> str:
    """Generate the complete blog template markdown."""
    parts = []
    
    # Add front matter
    parts.append(build_blog_frontmatter(template_data))
    
    # Add intro TODO section
    parts.append("TODO: Write an engaging introduction that sets up the story/content below.")
    parts.append("")
    
    # Add all template sections
    for status_idx, section in enumerate(template_data.sections):
        # Create the comment block with original content
        comment_lines = [
            "<!-- Original toot content:",
            f"{section.timestamp} - {section.original_content}"
        ]
        
        # Add alt text information if images exist
        if section.images:
            comment_lines.append("")
            comment_lines.append("Alt text for images:")
            for idx, img in enumerate(section.images, start=1):
                comment_lines.append(f"- Image {idx}: {img.alt_text}")
        
        comment_lines.append("-->")
        
        # Build the template section
        section_parts = [
            "## Section",
            "",
            "\n".join(comment_lines),
            "",
            section.original_content,
            ""
        ]
        
        # Add inline images if they exist
        if section.images:
            image_markdown = format_inline_images(section.images)
            section_parts.append(image_markdown)
            section_parts.append("")
        
        parts.extend(section_parts)
    
    # Add attribution footer
    if template_data.source_urls:
        parts.append(create_attribution_footer(template_data.source_urls))
    
    return "\n".join(parts)


def format_body(status: dict, assets_rel_dir: str, assets_path: Path) -> str:
    # header line
    acct = status.get("account", {}).get("acct") or status.get("account", {}).get("display_name") or "(unknown)"
    created = status.get("created_at", "")
    status_id = status.get("id")
    header = f"## Toot — {created} — @{acct}\n"

    # content
    content_html = status.get("content", "")
    content_md = html_to_markdown_basic(content_html)

    parts = [header, content_md, ""]

    # media attachments
    media = status.get("media_attachments", []) or []
    if media:
        parts.append("Media:\n")
        for idx, m in enumerate(media, start=1):
            remote = m.get("url") or m.get("preview_url")
            if not remote:
                continue
            orig_name = Path(remote).name
            filename = sanitize_filename(f"{status_id}_{idx}_{orig_name}")
            rel = f"{assets_rel_dir}/{filename}"
            # use media description (alt text) when available
            desc = m.get("description") or ""
            desc_md = html_to_markdown_basic(desc) if desc else ""
            alt_text = desc_md or filename
            parts.append(f"![{alt_text}]({rel})")
            parts.append(f"(original URL: {remote})")
            if desc_md:
                parts.append(f"*Alt text:* {desc_md}")
            parts.append("")

    return "\n".join(parts)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch a Mastodon toot and create a Markdown file with assets.")
    parser.add_argument("urls", nargs="*", help="Full status URLs (e.g. https://mastodon.social/@user/115260608425298248). Multiple URLs can be provided to combine threads.")
    parser.add_argument("--output-dir", default='.', help="Base directory to write the dated output folder with .md and assets (default: current working directory)")
    args = parser.parse_args(argv)

    try:
        all_statuses = []
        all_source_urls = []

        # Require explicit URLs only (no legacy --instance/--id use)
        if not args.urls:
            parser.error("Provide one or more status URLs (e.g. https://mastodon.social/@user/115260608425298248)")

        # Process each provided URL as a separate thread to include
        for url in args.urls:
            instance, status_id = parse_status_url(url)

            # Fetch the status and its context (ancestors) for this URL
            status = fetch_status(instance, status_id)
            ctx = fetch_context(instance, status_id)
            ancestors = ctx.get("ancestors", []) or []

            # Sort ancestors oldest -> newest explicitly
            try:
                ancestors_sorted = sorted(ancestors, key=lambda s: _parse_created_at(s.get("created_at", "")))
            except Exception:
                ancestors_sorted = ancestors[::-1]

            # Build the full thread: ancestors (oldest->newest) then the provided status (tail)
            thread_statuses = ancestors_sorted + [status]

            # Determine the head (oldest) status id for this thread and record its public URL
            if thread_statuses:
                head = thread_statuses[0]
                head_id = head.get("id")
                if head_id:
                    head_url = f"https://{instance}/@/{head_id}"
                    all_source_urls.append(head_url)

            # Add all statuses from this thread to the combined list
            all_statuses.extend(thread_statuses)

        # Remove duplicates (same status ID) and sort all statuses by creation time
        seen_ids = set()
        unique_statuses = []
        for status in all_statuses:
            status_id = status.get("id")
            if status_id and status_id not in seen_ids:
                seen_ids.add(status_id)
                unique_statuses.append(status)
        
        # Sort all statuses chronologically
        try:
            combined = sorted(unique_statuses, key=lambda s: _parse_created_at(s.get("created_at", "")))
        except Exception:
            combined = unique_statuses

        # prepare output paths
        base_out_dir = Path(args.output_dir)

        # name output folder by date (YYYY-MM-DD) of the oldest post in the combined thread
        if not combined:
            raise ValueError("No statuses found")
        
        oldest = combined[0]
        date_prefix = (oldest.get("created_at", "")[:10]) or "date"
        out_dir = base_out_dir / sanitize_filename(date_prefix)
        
        # Always generate the blog template format
        use_template = True

        # Always use index.md for Hugo page bundles
        md_filename = "index.md"
            
        md_path = out_dir / md_filename
        # Put assets in the same directory as the markdown file
        assets_abs_dir = out_dir
        assets_abs_dir.mkdir(parents=True, exist_ok=True)

        # download media for each status
        all_ids = []
        for st in combined:
            sid = st.get("id")
            all_ids.append(sid)
            media = st.get("media_attachments", []) or []
            for idx, m in enumerate(media, start=1):
                remote = m.get("url") or m.get("preview_url")
                if not remote:
                    continue
                orig_name = Path(remote).name
                filename = sanitize_filename(f"{sid}_{idx}_{orig_name}")
                dest = assets_abs_dir / filename
                try:
                    print(f"Downloading {remote} -> {dest}")
                    download_media(remote, dest)
                except Exception as ex:
                    print(f"Warning: failed to download media {remote}: {ex}", file=sys.stderr)

        # Generate content (template-only)
        template_data = build_template_from_statuses(combined, all_source_urls)
        content = generate_blog_template(template_data)

        md_path.parent.mkdir(parents=True, exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(content)

        print(f"Wrote: {md_path}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
