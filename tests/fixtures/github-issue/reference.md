Before Submitting

 I searched open and closed issues and discussions for an existing request.

 I checked whether this already exists on the dev branch or latest source.

 I understand that maintainers want a well-written issue or discussion before any code pull request.

 This request is not a security vulnerability.

Problem

v0.12.4 removed the quick actions (Archive, Delete) in the chat list that appeared when holding shift, in favor of multi-selection (#32543).

Desired Behavior

I'd like to see these functionality restored under a different keybinding - customizable if possible, but not strictly needed.

Why This Matters

Less clicks for frequent actions without having to use the mutli-selection UI.

Examples or References

No response

Alternatives or Workarounds

No response

Before Submitting

 I searched open and closed issues and discussions for an existing request.

 I checked whether this already exists on the dev branch or latest source.

 I understand that maintainers want a well-written issue or discussion before any code pull request.

 This request is not a security vulnerability.

Problem

v0.12.4 removed the quick actions (Archive, Delete) in the chat list that appeared when holding shift, in favor of multi-selection (#32543).

Desired Behavior

I'd like to see these functionality restored under a different keybinding - customizable if possible, but not strictly needed.

Why This Matters

Less clicks for frequent actions without having to use the mutli-selection UI.

Examples or References

No response

Alternatives or Workarounds

No response

🔍 Related Issues Found

I found some existing issues that might be related. Please check if any of these are duplicates or contain helpful solutions:

🟣 #32543 feat: Deleting multiple chats at once

This issue is the direct precursor to the behavior change described here: multi-selection replaced the older shift-based quick actions, and the user explicitly references feat: Deleting multiple chats at once #32543 as the reason the actions disappeared.

by jayc1323 · enhancement

🟣 #31932 feat: Add "Delete all" and "Archive all" mass-actions

This is closely related because it added bulk delete/archive actions for chats. It addresses the same chat-management area and reflects the broader desire for faster mass actions that the new request is trying to preserve, though with a different UI pattern.

by jk779 · enhancement

🟣 #30164 issue: the Delete Chat shortcut only works while the open chat's row is rendered in the sidebar

This is related because it concerns keyboard-driven delete behavior for chats and shows that the project already has issues around chat quick actions / shortcuts being tied to sidebar rendering. While not the same feature, it is in the same interaction area and may inform restoring alternate keybindings.

by silentoplayz · bug, confirmed issue

💡 If your issue is a duplicate, please close it and add any additional details to the existing issue instead.

This comment was generated automatically. React with 👍 if helpful, 👎 if not.

🔍 Related Issues Found

I found some existing issues that might be related. Please check if any of these are duplicates or contain helpful solutions:

🟣 #32543 feat: Deleting multiple chats at once

This issue is the direct precursor to the behavior change described here: multi-selection replaced the older shift-based quick actions, and the user explicitly references feat: Deleting multiple chats at once #32543 as the reason the actions disappeared.

by jayc1323 · enhancement

🟣 #31932 feat: Add "Delete all" and "Archive all" mass-actions

This is closely related because it added bulk delete/archive actions for chats. It addresses the same chat-management area and reflects the broader desire for faster mass actions that the new request is trying to preserve, though with a different UI pattern.

by jk779 · enhancement

🟣 #30164 issue: the Delete Chat shortcut only works while the open chat's row is rendered in the sidebar

This is related because it concerns keyboard-driven delete behavior for chats and shows that the project already has issues around chat quick actions / shortcuts being tied to sidebar rendering. While not the same feature, it is in the same interaction area and may inform restoring alternate keybindings.

by silentoplayz · bug, confirmed issue

💡 If your issue is a duplicate, please close it and add any additional details to the existing issue instead.

This comment was generated automatically. React with 👍 if helpful, 👎 if not.
