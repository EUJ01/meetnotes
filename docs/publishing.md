# Update files and publishing

## Update files

`projects/<project>/<key>_<date>_update.md`. The key is 99999999 minus the date as YYYYMMDD, so the newest update sorts first in any file list.

- The date comes from `--date`, else from the recording's file date. A downloaded recording has the download date, so pass `--date`.
- A second meeting on the same day gets `<key>_<date>_2_update.md`. Running the same recording again replaces its own file.
- The header names the recording's file name (never its folder). Rename a file such as `salary review.mp4` before you publish its update.

## Publishing

`meetnotes publish` sends every new or changed update file to each configured target. `.meetnotes/ledger.tsv` remembers what each target has, so a target that failed catches up on the next run. Deleting a local file does not delete the remote copy.

**Telegram**

1. Create a bot with @BotFather. Put its token in an environment variable: `TELEGRAM_BOT_TOKEN`.
2. Add the bot to your channel as an admin with the right to post (or to a group as a member).
3. Post any message in the channel, then run `meetnotes publish --list-chats` to see its id.
4. Map projects to chats:
   ```toml
   [publish.telegram.chats]
   weekly = "-100..."
   ```

**Google Drive, OneDrive, Dropbox, Syncthing**: with the desktop app, point at the synced folder. The folder must exist (an unmounted drive gives an error, not a new folder):

```toml
[publish.folder]
path = "G:/My Drive/meeting-notes"
```

**Any rclone remote** (a server without a Drive app): run `rclone config` once, then:

```toml
[publish.rclone]
remote = "gdrive:meeting-notes"
```
