from selectolax.parser import HTMLParser
from urllib.parse import urljoin
from typing import List, Dict, Any, Optional


class HTMLContentParser:
    """
    Parses HTML content and extracts structured data
    """
    
    def __init__(self, html: str, base_url: str):
        self.parser = HTMLParser(html)
        self.base_url = base_url
        self.section_counter = 0
    
    def extract_meta(self) -> Dict[str, Any]:
        """Extract metadata from HTML"""
        meta = {
            "title": "",
            "description": "",
            "language": "en",
            "canonical": None
        }
        
        # Extract title
        title_tag = self.parser.css_first("title")
        if title_tag:
            meta["title"] = title_tag.text(strip=True)
        
        # Try og:title as fallback
        if not meta["title"]:
            og_title = self.parser.css_first('meta[property="og:title"]')
            if og_title:
                meta["title"] = og_title.attributes.get("content", "")
        
        # Extract description
        desc_tag = self.parser.css_first('meta[name="description"]')
        if desc_tag:
            meta["description"] = desc_tag.attributes.get("content", "")
        
        # Try og:description as fallback
        if not meta["description"]:
            og_desc = self.parser.css_first('meta[property="og:description"]')
            if og_desc:
                meta["description"] = og_desc.attributes.get("content", "")
        
        # Extract language
        html_tag = self.parser.css_first("html")
        if html_tag and html_tag.attributes.get("lang"):
            meta["language"] = html_tag.attributes.get("lang", "en")
        
        # Extract canonical URL
        canonical_tag = self.parser.css_first('link[rel="canonical"]')
        if canonical_tag:
            meta["canonical"] = canonical_tag.attributes.get("href")
        
        return meta
    
    def extract_sections(self) -> List[Dict[str, Any]]:
        """Group content into sections"""
        sections = []
        
        # Try to find main content area
        main = self.parser.css_first("main, [role='main']")
        if main:
            sections.extend(self._parse_element_sections(main))
        else:
            # Parse body sections
            body = self.parser.css_first("body")
            if body:
                sections.extend(self._parse_body_sections(body))
        
        # If no sections found, create at least one
        if not sections:
            sections.append(self._create_fallback_section())
        
        return sections
    
    def _parse_body_sections(self, body) -> List[Dict[str, Any]]:
        """Parse sections from body element"""
        sections = []
        
        # Find landmark elements
        landmarks = body.css("header, nav, main, section, article, aside, footer")
        
        for element in landmarks:
            section = self._parse_section(element)
            if section and self._has_content(section):
                sections.append(section)
        
        return sections
    
    def _parse_element_sections(self, element) -> List[Dict[str, Any]]:
        """Parse sections from a specific element"""
        sections = []
        
        # Find sections and articles
        subsections = element.css("section, article, div[class*='section']")
        
        if subsections:
            for subsection in subsections:
                section = self._parse_section(subsection)
                if section and self._has_content(section):
                    sections.append(section)
        else:
            # Parse the element itself as a section
            section = self._parse_section(element)
            if section and self._has_content(section):
                sections.append(section)
        
        return sections
    
    def _parse_section(self, element) -> Optional[Dict[str, Any]]:
        """Parse a single section element"""
        self.section_counter += 1
        
        # Determine section type
        section_type = self._determine_section_type(element)
        
        # Extract content
        content = self._extract_content(element)
        
        # Generate label
        label = self._generate_label(element, content)
        
        # Get raw HTML (truncated)
        raw_html = element.html
        truncated = False
        if len(raw_html) > 5000:
            raw_html = raw_html[:5000] + "..."
            truncated = True
        
        return {
            "id": f"{section_type}-{self.section_counter}",
            "type": section_type,
            "label": label,
            "sourceUrl": self.base_url,
            "content": content,
            "rawHtml": raw_html,
            "truncated": truncated
        }
    
    def _determine_section_type(self, element) -> str:
        """Determine the type of section"""
        tag = element.tag.lower()
        classes = element.attributes.get("class", "").lower()
        id_attr = element.attributes.get("id", "").lower()
        
        # Check by tag
        if tag == "header":
            return "hero" if "hero" in classes else "section"
        if tag == "nav":
            return "nav"
        if tag == "footer":
            return "footer"
        
        # Check by class/id
        if any(keyword in classes or keyword in id_attr for keyword in ["hero", "banner", "jumbotron"]):
            return "hero"
        if any(keyword in classes or keyword in id_attr for keyword in ["pricing", "plans"]):
            return "pricing"
        if any(keyword in classes or keyword in id_attr for keyword in ["faq", "questions"]):
            return "faq"
        if "grid" in classes or "cards" in classes:
            return "grid"
        if any(keyword in classes or keyword in id_attr for keyword in ["nav", "menu"]):
            return "nav"
        
        # Check for lists
        if element.css("ul, ol"):
            return "list"
        
        return "section"
    
    def _extract_content(self, element) -> Dict[str, Any]:
        """Extract structured content from element"""
        content = {
            "headings": [],
            "text": "",
            "links": [],
            "images": [],
            "lists": [],
            "tables": []
        }
        
        # Extract headings
        for heading in element.css("h1, h2, h3, h4, h5, h6"):
            text = heading.text(strip=True)
            if text:
                content["headings"].append(text)
        
        # Extract text (remove script/style content)
        for script in element.css("script, style"):
            script.decompose()
        
        text = element.text(strip=True)
        content["text"] = text[:2000] if len(text) > 2000 else text
        
        # Extract links
        for link in element.css("a[href]"):
            href = link.attributes.get("href", "")
            if href and not href.startswith("#"):
                content["links"].append({
                    "text": link.text(strip=True),
                    "href": self._make_absolute_url(href)
                })
        
        # Extract images
        for img in element.css("img[src]"):
            src = img.attributes.get("src", "")
            if src:
                content["images"].append({
                    "src": self._make_absolute_url(src),
                    "alt": img.attributes.get("alt", "")
                })
        
        # Extract lists
        for ul in element.css("ul, ol"):
            items = [li.text(strip=True) for li in ul.css("li")]
            if items:
                content["lists"].append(items)
        
        # Extract tables
        for table in element.css("table"):
            table_data = self._parse_table(table)
            if table_data:
                content["tables"].append(table_data)
        
        return content
    
    def _parse_table(self, table) -> List[List[str]]:
        """Parse table into 2D array"""
        rows = []
        for tr in table.css("tr"):
            cells = [td.text(strip=True) for td in tr.css("td, th")]
            if cells:
                rows.append(cells)
        return rows
    
    def _generate_label(self, element, content: Dict[str, Any]) -> str:
        """Generate a label for the section"""
        # Try to use first heading
        if content["headings"]:
            return content["headings"][0][:50]
        
        # Try to use id or class
        id_attr = element.attributes.get("id", "")
        if id_attr:
            return id_attr.replace("-", " ").replace("_", " ").title()[:50]
        
        # Use first few words of text
        text = content["text"]
        if text:
            words = text.split()[:7]
            return " ".join(words) + ("..." if len(words) == 7 else "")
        
        return "Untitled Section"
    
    def _make_absolute_url(self, url: str) -> str:
        """Convert relative URLs to absolute"""
        if url.startswith(("http://", "https://")):
            return url
        return urljoin(self.base_url, url)
    
    def _has_content(self, section: Dict[str, Any]) -> bool:
        """Check if section has meaningful content"""
        content = section.get("content", {})
        return bool(
            content.get("headings") or
            len(content.get("text", "")) > 20 or
            content.get("links") or
            content.get("images")
        )
    
    def _create_fallback_section(self) -> Dict[str, Any]:
        """Create a fallback section when no sections found"""
        body = self.parser.css_first("body")
        if body:
            return self._parse_section(body)
        
        return {
            "id": "fallback-1",
            "type": "unknown",
            "label": "Page Content",
            "sourceUrl": self.base_url,
            "content": {
                "headings": [],
                "text": "No content extracted",
                "links": [],
                "images": [],
                "lists": [],
                "tables": []
            },
            "rawHtml": "",
            "truncated": False
        }