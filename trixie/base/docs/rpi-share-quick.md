# rpi-share – Quick Guide (Lab Users)

## 📦 Copy files to Aalto shared storage

---

## ▶️ 1. Start

Open terminal and run:

```bash
rpi-share
```

---

## 🧭 2. Follow the instructions

### Select your role

```text
1) Staff / staff status
2) Student
```

👉 Choose the option that applies to you

---

### Select server

```text
1) viila  (staff – recommended)
2) kosh   (students + staff)
```

👉 If unsure:

* staff → **viila**
* student → **kosh**

---

### Select storage location

Example:

```text
1) teamwork-chem   (recommended)
2) teamwork-cmet
3) work-t100
...
```

👉 Choose your group / project location

---

### Enter username

```text
username:
```

👉 Use your normal Aalto username

---

## 📂 3. Copy files

Open file manager:

```bash
nemo /media/rpi-share/...
```

Then:

👉 Drag & drop files
👉 Or copy/paste

---

## ⏳ 4. Wait until copy finishes

Do NOT close anything during transfer.

---

## 🔌 5. Disconnect

1. Close file manager windows
2. Return to terminal
3. Press:

```text
Enter
```

---

## 🔄 Typical workflow

```text
[ Instrument PC ] ─┐
                   ├──► rpi-share ───► Aalto shared storage (Teamwork / Work)
[ Raspberry Pi ] ──┤
                   │
[ Lab computer ] ──┘
```

---

## ⚠️ Important

* ❌ Do NOT store research data in personal home directory
* ✅ Use shared Teamwork or Work storage
* ❌ Do NOT unplug network during transfer
* ❌ Do NOT close terminal while copying

---

## 🧯 If something goes wrong

Check status:

```bash
rpi-share --status
```

Clean up:

```bash
rpi-share --cleanup
```

---

## 💡 Tips

* If one server does not work → try the other (`viila` / `kosh`)
* If access fails → you may not have permission
* Ask your supervisor or lab admin if unsure

---

## 🆘 Need help?

Contact your lab admin / Chem-IT
