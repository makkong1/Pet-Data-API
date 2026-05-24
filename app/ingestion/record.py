from dataclasses import dataclass, field


@dataclass
class PostRecord:
    title:       str
    description: str
    link:        str
    postdate:    str
    source:      str
    author_name: str = field(default="")
    author_link: str = field(default="")

    def to_dict(self) -> dict:
        return {
            "title":        self.title,
            "description":  self.description,
            "link":         self.link,
            "postdate":     self.postdate,
            "blogger_name": self.author_name,
            "blogger_link": self.author_link,
        }
