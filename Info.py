import customtkinter as ctk
import os
import sys
import platform
import threading
import webbrowser
import requests
from tkinter import messagebox
from datetime import datetime

# ================= GITHUB CONFIGURATION =================
REPO_OWNER = "YourGitHubUsername"
REPO_NAME = "YourRpgMakerRepo"
GITHUB_TOKEN = "github_pat_YOUR_TOKEN_HERE"
# ========================================================

API_BASE_URL = f"https://api.github.com/repos/m-13222742-source/Rpg-Creator-1/issues"

BUG_CATEGORIES = [
    "Engine Core",
    "Crash / Freeze",
    "DLL / Modules",
    "Plugin System",
    "UI / Visual",
    "Other",
]

SUGGESTION_CATEGORIES = [
    "Editor Feature",
    "Plugin API",
    "UI / UX",
    "Performance",
    "Audio / Graphics",
    "Other",
]

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class RpgInfoCenter(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("RPG Creator - Info & Community Feedback")
        self.geometry("760x600")
        self.resizable(False, False)

        # Resolve root directory whether running as .py or compiled Info.exe
        if getattr(sys, "frozen", False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.version_file = os.path.join(self.base_dir, "version.txt")
        self.engine_version = self.load_engine_version()
        self.system_info = f"{platform.system()} {platform.release()} ({platform.machine()})"

        self.build_ui()
        self.fetch_posts()

    def load_engine_version(self):
        """Reads the installed RPG Creator version from version.txt."""
        if os.path.exists(self.version_file):
            try:
                with open(self.version_file, "r") as f:
                    ver = f.read().strip()
                    if ver:
                        return ver
            except Exception:
                pass
        return "Unknown Version"

    def get_headers(self, include_auth=True):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if include_auth and GITHUB_TOKEN and "YOUR_TOKEN_HERE" not in GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        return headers

    def build_ui(self):
        # Top Header
        header_frame = ctk.CTkFrame(self, fg_color="#1a1a1a", corner_radius=0)
        header_frame.pack(fill="x")

        ctk.CTkLabel(
            header_frame,
            text="RPG Creator Info & Community Hub",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=20, pady=12)

        ctk.CTkLabel(
            header_frame,
            text=f"Build: {self.engine_version}",
            text_color="#00FF00",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="right", padx=20, pady=12)

        # Tabbed Interface
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        self.tab_feed = self.tabview.add("Community Feed")
        self.tab_submit = self.tabview.add("Submit Bug / Suggestion")

        self.build_feed_tab()
        self.build_submit_tab()

    # ================= TAB 1: COMMUNITY FEED =================

    def build_feed_tab(self):
        toolbar = ctk.CTkFrame(self.tab_feed, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 8))

        self.feed_status_label = ctk.CTkLabel(
            toolbar, text="Syncing with GitHub...", text_color="gray"
        )
        self.feed_status_label.pack(side="left")

        self.refresh_btn = ctk.CTkButton(
            toolbar, text="Refresh", width=90, command=self.fetch_posts
        )
        self.refresh_btn.pack(side="right")

        # Status Filter (All / Open / Closed)
        self.state_filter_var = ctk.StringVar(value="all")
        ctk.CTkOptionMenu(
            toolbar,
            variable=self.state_filter_var,
            values=["all", "open", "closed"],
            width=90,
            command=lambda _: self.fetch_posts(),
        ).pack(side="right", padx=(0, 8))

        # Type Filter (All Posts / Bugs / Suggestions)
        self.type_filter_var = ctk.StringVar(value="All Posts")
        ctk.CTkOptionMenu(
            toolbar,
            variable=self.type_filter_var,
            values=["All Posts", "Bugs", "Suggestions"],
            width=120,
            command=lambda _: self.fetch_posts(),
        ).pack(side="right", padx=(0, 8))

        self.feed_scroll = ctk.CTkScrollableFrame(self.tab_feed, fg_color="#141414")
        self.feed_scroll.pack(fill="both", expand=True)

    def fetch_posts(self):
        self.refresh_btn.configure(state="disabled")
        self.feed_status_label.configure(text="Syncing with GitHub...", text_color="gray")
        state_filter = self.state_filter_var.get()
        type_filter = self.type_filter_var.get()
        threading.Thread(
            target=self._fetch_posts_worker,
            args=(state_filter, type_filter),
            daemon=True,
        ).start()

    def _fetch_posts_worker(self, state_filter, type_filter):
        try:
            params = {"state": state_filter, "per_page": 60}
            if type_filter == "Bugs":
                params["labels"] = "bug"
            elif type_filter == "Suggestions":
                params["labels"] = "enhancement"

            response = requests.get(
                API_BASE_URL,
                headers=self.get_headers(include_auth=True),
                params=params,
                timeout=10,
            )
            response.raise_for_status()

            filtered_issues = []
            for item in response.json():
                if "pull_request" in item:
                    continue
                label_names = [lbl.get("name", "").lower() for lbl in item.get("labels", [])]
                # Only show community Bugs and Suggestions (ignores unlabeled dev tasks)
                if "bug" in label_names or "enhancement" in label_names:
                    filtered_issues.append(item)

            self.after(0, lambda: self.render_feed(filtered_issues))
        except Exception as e:
            self.after(0, lambda: self.handle_fetch_error(str(e)))

    def handle_fetch_error(self, error_msg):
        self.refresh_btn.configure(state="normal")
        self.feed_status_label.configure(
            text="Failed to connect to GitHub.", text_color="#FF4444"
        )
        for widget in self.feed_scroll.winfo_children():
            widget.destroy()
        ctk.CTkLabel(
            self.feed_scroll,
            text=f"GitHub Connection Error:\n{error_msg}",
            text_color="#FF4444",
            wraplength=640,
        ).pack(pady=40)

    def render_feed(self, issues):
        self.refresh_btn.configure(state="normal")
        for widget in self.feed_scroll.winfo_children():
            widget.destroy()

        if not issues:
            self.feed_status_label.configure(text="0 posts found.", text_color="gray")
            ctk.CTkLabel(
                self.feed_scroll,
                text="No bugs or suggestions found for this filter.",
                text_color="gray",
            ).pack(pady=40)
            return

        self.feed_status_label.configure(
            text=f"Showing {len(issues)} community post(s)", text_color="gray"
        )

        for issue in issues:
            card = ctk.CTkFrame(self.feed_scroll, fg_color="#1f1f1f", corner_radius=8)
            card.pack(fill="x", padx=6, pady=6)

            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=12, pady=(10, 2))

            label_names = [lbl.get("name", "") for lbl in issue.get("labels", [])]
            lower_labels = [name.lower() for name in label_names]

            # Post Type Badge
            is_suggestion = "enhancement" in lower_labels and "bug" not in lower_labels
            type_text = "[SUGGESTION]" if is_suggestion else "[BUG]"
            type_color = "#38BDF8" if is_suggestion else "#F87171"

            ctk.CTkLabel(
                top_row,
                text=type_text,
                text_color=type_color,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=(0, 6))

            # Open / Closed Status Badge
            is_open = issue.get("state") == "open"
            status_text = (
                "[OPEN]"
                if is_open
                else ("[IMPLEMENTED]" if is_suggestion else "[FIXED]")
            )
            status_color = "#FFA500" if is_open else "#00FF00"

            ctk.CTkLabel(
                top_row,
                text=f"#{issue.get('number')} {status_text}",
                text_color=status_color,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=(0, 8))

            ctk.CTkLabel(
                top_row,
                text=issue.get("title", "Untitled"),
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(side="left")

            issue_url = issue.get("html_url", "")
            if issue_url:
                ctk.CTkButton(
                    top_row,
                    text="View Thread",
                    width=85,
                    height=24,
                    fg_color="#333333",
                    hover_color="#444444",
                    font=ctk.CTkFont(size=11),
                    command=lambda url=issue_url: webbrowser.open(url),
                ).pack(side="right")

            # Tags & Date Metadata
            display_tags = [
                lbl for lbl in label_names if lbl.lower() not in ("bug", "enhancement")
            ]
            tag_str = f"Category: {', '.join(display_tags)}  |  " if display_tags else ""
            created_at = issue.get("created_at", "")[:10]
            comments_count = issue.get("comments", 0)

            meta_text = f"{tag_str}Posted: {created_at}  |  Replies: {comments_count}"
            ctk.CTkLabel(
                card,
                text=meta_text,
                text_color="gray",
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=12, pady=(0, 6))

            raw_body = issue.get("body") or "No details provided."
            clean_body = raw_body.replace("### ", "").replace("**", "")

            ctk.CTkLabel(
                card,
                text=clean_body,
                justify="left",
                wraplength=670,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=12, pady=(0, 10))

    # ================= TAB 2: SUBMIT BUG OR SUGGESTION =================

    def build_submit_tab(self):
        form = ctk.CTkFrame(self.tab_submit, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=10, pady=5)

        # Post Type Selector
        type_row = ctk.CTkFrame(form, fg_color="transparent")
        type_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            type_row,
            text="What would you like to share?",
            font=ctk.CTkFont(weight="bold"),
        ).pack(side="left", padx=(0, 15))

        self.post_type_var = ctk.StringVar(value="Bug Report")
        self.type_selector = ctk.CTkSegmentedButton(
            type_row,
            values=["Bug Report", "Suggestion"],
            variable=self.post_type_var,
            command=self.on_post_type_change,
        )
        self.type_selector.pack(side="left")

        # Author & Category
        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 10))

        author_col = ctk.CTkFrame(row1, fg_color="transparent")
        author_col.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(author_col, text="Your Name / Handle:").pack(anchor="w")
        self.author_entry = ctk.CTkEntry(author_col, placeholder_text="Anonymous")
        self.author_entry.pack(fill="x", pady=(2, 0))

        cat_col = ctk.CTkFrame(row1, fg_color="transparent")
        cat_col.pack(side="right", fill="x", expand=True, padx=(10, 0))
        ctk.CTkLabel(cat_col, text="Category:").pack(anchor="w")
        self.category_var = ctk.StringVar(value=BUG_CATEGORIES[0])
        self.category_menu = ctk.CTkOptionMenu(
            cat_col,
            variable=self.category_var,
            values=BUG_CATEGORIES,
        )
        self.category_menu.pack(fill="x", pady=(2, 0))

        # Summary Title
        self.title_label = ctk.CTkLabel(form, text="Bug Summary:")
        self.title_label.pack(anchor="w")
        self.title_entry = ctk.CTkEntry(
            form, placeholder_text="e.g., Engine crashes when loading custom physics DLL"
        )
        self.title_entry.pack(fill="x", pady=(2, 10))

        # Description
        self.desc_label = ctk.CTkLabel(
            form, text="Detailed Description & Steps to Reproduce:"
        )
        self.desc_label.pack(anchor="w")
        self.desc_textbox = ctk.CTkTextbox(form, height=165, wrap="word")
        self.desc_textbox.pack(fill="both", expand=True, pady=(2, 10))

        # Footer: Auto-attached Diagnostics + Submit Button
        footer = ctk.CTkFrame(form, fg_color="transparent")
        footer.pack(fill="x")

        diag_text = f"Auto-attached: {self.engine_version} • {self.system_info}"
        ctk.CTkLabel(
            footer, text=diag_text, text_color="gray", font=ctk.CTkFont(size=11)
        ).pack(side="left")

        self.submit_btn = ctk.CTkButton(
            footer,
            text="Post to GitHub",
            font=ctk.CTkFont(weight="bold"),
            command=self.submit_post,
        )
        self.submit_btn.pack(side="right")

    def on_post_type_change(self, selected_type):
        if selected_type == "Bug Report":
            self.category_menu.configure(values=BUG_CATEGORIES)
            self.category_var.set(BUG_CATEGORIES[0])
            self.title_label.configure(text="Bug Summary:")
            self.title_entry.configure(
                placeholder_text="e.g., Engine crashes when loading custom physics DLL"
            )
            self.desc_label.configure(text="Detailed Description & Steps to Reproduce:")
        else:
            self.category_menu.configure(values=SUGGESTION_CATEGORIES)
            self.category_var.set(SUGGESTION_CATEGORIES[0])
            self.title_label.configure(text="Suggestion Title:")
            self.title_entry.configure(
                placeholder_text="e.g., Add tilemap auto-tiling brush tool"
            )
            self.desc_label.configure(text="Describe your idea and how it would help:")

    def submit_post(self):
        if "YOUR_TOKEN_HERE" in GITHUB_TOKEN:
            messagebox.showerror(
                "Configuration Missing",
                "Set your GITHUB_TOKEN, REPO_OWNER, and REPO_NAME at the top of Info.py first.",
            )
            return

        post_type = self.post_type_var.get()
        title = self.title_entry.get().strip()
        description = self.desc_textbox.get("0.0", "end").strip()
        author = self.author_entry.get().strip() or "Anonymous"
        category = self.category_var.get()

        if not title or not description:
            messagebox.showwarning(
                "Missing Details", "Please provide both a summary and a description."
            )
            return

        is_bug = post_type == "Bug Report"
        primary_label = "bug" if is_bug else "enhancement"
        section_heading = "Description" if is_bug else "Suggestion Details"

        formatted_body = (
            f"**Type:** {post_type}\n"
            f"**Submitted By:** {author[:40]}\n"
            f"**Engine Version:** `{self.engine_version}`\n"
            f"**System Info:** `{self.system_info}`\n"
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"### {section_heading}\n{description}"
        )

        payload = {
            "title": f"[{self.engine_version}] {title}",
            "body": formatted_body,
            "labels": [primary_label, category],
        }

        self.submit_btn.configure(state="disabled", text="Posting...")
        threading.Thread(
            target=self._submit_post_worker, args=(payload, post_type), daemon=True
        ).start()

    def _submit_post_worker(self, payload, post_type):
        try:
            response = requests.post(
                API_BASE_URL,
                headers=self.get_headers(include_auth=True),
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            issue_data = response.json()
            self.after(0, lambda: self.on_submit_success(issue_data, post_type))
        except Exception as e:
            self.after(0, lambda: self.on_submit_error(str(e)))

    def on_submit_success(self, issue_data, post_type):
        self.submit_btn.configure(state="normal", text="Post to GitHub")
        self.title_entry.delete(0, "end")
        self.desc_textbox.delete("0.0", "end")
        issue_num = issue_data.get("number", "")
        messagebox.showinfo(
            "Posted",
            f"Your {post_type.lower()} (#{issue_num}) is now live on the Community Feed!",
        )
        self.tabview.set("Community Feed")
        self.fetch_posts()

    def on_submit_error(self, error_msg):
        self.submit_btn.configure(state="normal", text="Post to GitHub")
        messagebox.showerror("Submission Failed", f"GitHub API Error:\n{error_msg}")


if __name__ == "__main__":
    app = RpgInfoCenter()
    app.mainloop()
