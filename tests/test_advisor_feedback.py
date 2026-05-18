import unittest
from unittest.mock import patch

import claude_any


class AdvisorFeedbackTests(unittest.TestCase):
    def test_internal_advisor_feedback_is_sent_back_to_main_model_body(self):
        body = {"messages": [{"role": "user", "content": "build the feature"}]}
        assistant_message = {
            "role": "assistant",
            "content": [{"type": "text", "text": "I will exit plan mode."}],
        }

        follow_body = claude_any.body_with_internal_advisor_feedback(
            body,
            assistant_message,
            "Check the migration plan before approval.",
            "before ExitPlanMode plan approval",
        )

        feedback_text = claude_any.anthropic_content_to_text(follow_body["messages"][-1]["content"])
        self.assertIn(claude_any.ADVISOR_FEEDBACK_MARKER, feedback_text)
        self.assertIn("Check the migration plan before approval.", feedback_text)
        self.assertIn("Apply this advisor feedback now.", feedback_text)

    def test_refined_message_includes_visible_advisor_summary(self):
        body = {"messages": [{"role": "user", "content": "build the feature"}]}
        assistant_message = {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_plan",
                    "name": "ExitPlanMode",
                    "input": {"plan": "ship it"},
                }
            ],
            "stop_reason": "tool_use",
        }
        refined = {
            "role": "assistant",
            "content": [{"type": "text", "text": "Updated plan is ready."}],
            "stop_reason": "end_turn",
        }

        with (
            patch("claude_any.advisor_model_enabled", return_value="deepseek-v4-pro"),
            patch("claude_any.advisor_provider_supported", return_value=True),
            patch("claude_any.call_advisor_text", return_value="The plan needs a validation step.") as advisor_call,
            patch("claude_any.call_provider_chat_once", return_value=refined) as main_call,
        ):
            out = claude_any.refine_message_with_advisor(
                "ollama-cloud",
                {"advisor_model": "deepseek-v4-pro"},
                body,
                assistant_message,
                "main-model",
            )

        advisor_focus = advisor_call.call_args.kwargs["focus"]
        self.assertIn("ExitPlanMode plan before user approval", advisor_focus)
        self.assertIn("ship it", advisor_focus)
        self.assertTrue(main_call.called)
        sent_body = main_call.call_args.args[2]
        sent_text = claude_any.anthropic_content_to_text(sent_body["messages"][-1]["content"])
        self.assertIn("The plan needs a validation step.", sent_text)
        assistant_summary = claude_any.anthropic_content_to_text(sent_body["messages"][-2]["content"])
        self.assertIn("Pending Claude Code tool call: ExitPlanMode", assistant_summary)
        self.assertIn("ship it", assistant_summary)
        visible = claude_any.anthropic_content_to_text(out["content"])
        self.assertIn("Advisor review (before ExitPlanMode plan approval):", visible)
        self.assertIn("The plan needs a validation step.", visible)
        self.assertIn("Updated plan is ready.", visible)

    def test_advisor_prompt_requires_actual_verdict(self):
        self.assertIn("Review now", claude_any.ADVISOR_REVIEW_PROMPT)
        self.assertIn("Verdict:", claude_any.ADVISOR_REVIEW_PROMPT)
        self.assertIn("Required next action:", claude_any.ADVISOR_REVIEW_PROMPT)

    def test_advisor_visible_summary_is_bounded(self):
        text = claude_any.advisor_visible_summary("x" * 1000, "trigger", limit=80)

        self.assertLessEqual(len(text), 120)
        self.assertIn("Advisor review (trigger):", text)
        self.assertIn("…", text)


if __name__ == "__main__":
    unittest.main()
