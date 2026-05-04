from job_agent.parsers.registry import ParserRegistry


GREENHOUSE_HTML = """
<html>
  <head>
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "AI Engineer Intern",
        "description": "Work on LLM and machine learning systems.",
        "hiringOrganization": {"name": "Example AI"},
        "jobLocation": {"address": {"addressLocality": "San Francisco", "addressRegion": "CA", "addressCountry": "US"}}
      }
    </script>
  </head>
  <body></body>
</html>
"""


def test_registry_parses_greenhouse_jobposting_jsonld():
    registry = ParserRegistry()

    job = registry.parse(
        GREENHOUSE_HTML,
        "https://boards.greenhouse.io/example/jobs/12345",
    )

    assert job.title == "AI Engineer Intern"
    assert job.company == "Example AI"
    assert "San Francisco" in job.location
