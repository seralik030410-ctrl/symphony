# Static site acceptance checklist

- One descriptive `h1` and a meaningful document title.
- Landmarks (`header`, `main`, `nav`, `footer`) where appropriate.
- Controls are reachable by keyboard and have visible focus.
- Text and controls remain usable at 375, 768 and 1440 CSS pixels.
- Local CSS and JavaScript assets resolve from `dist/index.html`.
- Tests assert user-visible requirements rather than only file existence.
- The build performs real copying/transformation and fails on error.
