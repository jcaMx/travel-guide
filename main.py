from nicegui import ui
from datetime import datetime
import json, os, anyio
from typing import Any, Dict
from langchain_openai import ChatOpenAI

# ===== Lazy LLM =====
def get_llm():
    return ChatOpenAI(model="gpt-4o-mini")  # requires OPENAI_API_KEY

os.makedirs("travel-guide-output", exist_ok=True)

# ===== Example Config =====
CONFIG_JSON = """
{
  "title": "✈ PERSONALIZED ACTIVITY GUIDE",
  "subtitle": "Create custom travel itineraries tailored to your preferences",
  "sections": [
    {
      "title": "GUEST INFORMATION",
      "layout": "row",
      "fields": [
        {"id": "first_name", "label": "First Name", "type": "text", "width": "w-1/4"},
        {"id": "last_name", "label": "Last Name", "type": "text", "width": "w-1/4"},
        {"id": "guests", "label": "Guests", "type": "number", "width": "w-1/6", "default": 2, "props": {"min": 1}},
        {"id": "destination", "label": "Destination City", "type": "text", "width": "w-1/3"}
      ]
    },
    {
      "title": "TRAVEL DATES",
      "layout": "row",
      "fields": [
        {"id": "check_in", "label": "Check In", "type": "date", "width": "w-1/2"},
        {"id": "check_out", "label": "Check Out", "type": "date", "width": "w-1/2"}
      ]
    },
    {
      "title": "PREFERENCES",
      "layout": "two_cards",
      "cards": [
        {
          "title": "Activity Interests",
          "fields": [
            {"id": "relaxation", "label": "Relaxation", "type": "checkbox"},
            {"id": "adventure", "label": "Adventure", "type": "checkbox"},
            {"id": "family", "label": "Family-Friendly", "type": "checkbox"},
            {"id": "cultural", "label": "Cultural", "type": "checkbox"},
            {"id": "food", "label": "Food & Drink", "type": "checkbox"}
          ]
        },
        {
          "title": "Transportation",
          "fields": [
            {"id": "car", "label": "Car Rental", "type": "checkbox"},
            {"id": "rideshare", "label": "Ride Share", "type": "checkbox"},
            {"id": "metro", "label": "Metro / Bus", "type": "checkbox"},
            {"id": "bike", "label": "Bike", "type": "checkbox"},
            {"id": "walk", "label": "Walk", "type": "checkbox"}
          ]
        }
      ]
    }
  ],
  "primary_action": {"label": "Generate Guide"}
}
"""

# ===== Dynamic Renderer =====
WidgetRef = Dict[str, Any]

def render_field(field: Dict[str, Any], widgets: WidgetRef):
    t = field.get("type", "text")
    label = field.get("label", "")
    width = field.get("width", "w-full")
    default = field.get("default")
    props = field.get("props", {})

    if t == "text":
        w = ui.input(label, value=default).classes(width)
    elif t == "number":
        min_val = props.get("min", None)
        max_val = props.get("max", None)
        w = ui.number(label, value=default, min=min_val, max=max_val).classes(width)
    elif t == "date":
        w = ui.input(label).props("type=date").classes(width)
    elif t == "checkbox":
        w = ui.checkbox(label, value=bool(default))
    else:
        w = ui.input(label, value=default).classes(width)

    widgets[field["id"]] = w
    return w

def collect_values(widgets: WidgetRef) -> Dict[str, Any]:
    return {fid: getattr(w, "value", None) for fid, w in widgets.items()}

# ===== Shared result state =====
result_data = {"content": "", "title": ""}

# ===== Pages =====
def build_ui(config: Dict[str, Any], widgets: WidgetRef):
    with ui.card().classes("max-w-3xl mx-auto p-6 space-y-2"):
        ui.label(config.get("title", "Dynamic Form")).classes("text-2xl font-bold text-center")
        if config.get("subtitle"):
            ui.label(config["subtitle"]).classes("text-sm text-center text-gray-500")

        for i, section in enumerate(config.get("sections", [])):
            if i > 0: ui.separator()
            ui.label(section.get("title", "")).classes("text-lg font-semibold text-center")

            layout = section.get("layout", "row")
            if layout == "row":
                with ui.row().classes("w-full justify-between"):
                    for f in section.get("fields", []):
                        render_field(f, widgets)
            elif layout == "two_cards":
                with ui.row().classes("grid grid-cols-1 md:grid-cols-2 gap-4 w-full"):
                    for card in section.get("cards", []):
                        with ui.card().classes("p-3"):
                            ui.label(card["title"]).classes("font-semibold")
                            for f in card.get("fields", []):
                                render_field(f, widgets)

        action_label = config.get("primary_action", {}).get("label", "Submit")
        ui.button(action_label, on_click=lambda: generate_guide(widgets)).classes(
            "w-full bg-black text-white mt-4 p-3 rounded-lg"
        )


@ui.page("/result")
def result_page():
    ui.label(result_data["title"]).classes("text-xl font-bold")
    ui.markdown(result_data["content"]).classes("prose max-w-none")
    ui.button("⬅ Back", on_click=lambda: ui.navigate.to("/"))

# ===== Guide Generation =====
async def generate_guide(widgets: WidgetRef):
    values = collect_values(widgets)
    fname = values.get("first_name") or ""
    lname = values.get("last_name") or ""
    dest = values.get("destination") or ""
    guests = values.get("guests") or "N/A"
    check_in = values.get("check_in") or ""
    check_out = values.get("check_out") or ""

    if not fname or not dest:
        ui.notify("❌ Please fill in at least First Name and Destination.", color="negative")
        return

    try:
        checkin_date = datetime.fromisoformat(check_in) if check_in else None
        checkout_date = datetime.fromisoformat(check_out) if check_out else None
    except Exception:
        checkin_date = checkout_date = None

    if checkin_date and checkout_date and checkout_date <= checkin_date:
        ui.notify("❌ Check-out must be after check-in.", color="negative")
        return

    days = (checkout_date - checkin_date).days if checkin_date and checkout_date else 3
    selected_activities = [fid for fid in ["relaxation","adventure","family","cultural","food"] if values.get(fid)]
    selected_transports = [fid for fid in ["car","rideshare","metro","bike","walk"] if values.get(fid)]

    prompt = f"""
    Create a comprehensive travel activity guide for {dest} lasting {days} days.
    Traveler: {fname} {lname}, Party Size: {guests}, Dates: {check_in} → {check_out}
    Activities: {", ".join(selected_activities) or "Open to all experiences"}
    Transportation: {", ".join(selected_transports) or "Flexible"}
    """

    # Loading dialog
    with ui.dialog() as d, ui.card():
        ui.label("⏳ Generating guide...")
    d.open()

    # Run LLM in background thread
    def run_llm():
        llm = get_llm()
        return llm.invoke(prompt).content.strip()

    result = await anyio.to_thread.run_sync(run_llm)
    d.close()

    # Save to file
    filename = f"travel-guide-output/travel_guide_{fname}_{lname}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(result)

    # Update shared state
    result_data["title"] = f"📝 Guide for {fname} {lname} in {dest} ({days} days)"
    result_data["content"] = result

    ui.navigate.to("/result")
    ui.notify(f"✅ Saved as {filename}", color="positive")

# ===== Run App =====
def main():
    widgets: WidgetRef = {}
    config = json.loads(CONFIG_JSON)
    build_ui(config, widgets)
    ui.run(reload=False, native=False)  # set native=True if pywebview installed

if __name__ in {"__main__", "__mp_main__"}:
    main()
