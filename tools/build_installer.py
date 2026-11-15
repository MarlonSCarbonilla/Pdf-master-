"""Build a standalone Windows GUI Installer (dist/PDFMaster-Setup.exe) using the built-in
Windows .NET C# compiler (csc.exe) and ZipArchive payload — 100% offline, no external tools required."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile

CSC_PATHS = (
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
)

UNINSTALLER_CS = r"""
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using Microsoft.Win32;

namespace PDFMasterUninstaller
{
    static class Program
    {
        [STAThread]
        static int Main(string[] args)
        {
            bool silent = false;
            foreach (string a in args)
            {
                if (a.Equals("/S", StringComparison.OrdinalIgnoreCase) ||
                    a.Equals("/SILENT", StringComparison.OrdinalIgnoreCase))
                    silent = true;
            }

            string appDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
            if (!silent)
            {
                var res = MessageBox.Show(
                    "Are you sure you want to completely remove PDF Master from your computer?\n\n" +
                    "(Your personal PDF documents will not be deleted.)",
                    "Uninstall PDF Master",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Question
                );
                if (res != DialogResult.Yes)
                    return 0;
            }

            try
            {
                string desktopLnk = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "PDF Master.lnk");
                if (File.Exists(desktopLnk)) File.Delete(desktopLnk);

                string startMenuDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "PDF Master");
                if (Directory.Exists(startMenuDir)) Directory.Delete(startMenuDir, true);

                Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\PDFMaster", false);
            }
            catch { }

            // Schedule self-deletion of installation folder via cmd.exe after process exits
            try
            {
                var psi = new ProcessStartInfo("cmd.exe", "/C ping 127.0.0.1 -n 2 > nul & rmdir /S /Q \"" + appDir + "\"")
                {
                    WindowStyle = ProcessWindowStyle.Hidden,
                    CreateNoWindow = true,
                    UseShellExecute = false
                };
                Process.Start(psi);
            }
            catch { }

            if (!silent)
            {
                MessageBox.Show("PDF Master has been uninstalled.", "Uninstall PDF Master", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            return 0;
        }
    }
}
"""

SETUP_CS = r"""
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("PDF Master Setup")]
[assembly: AssemblyDescription("PDF Master - Offline PDF Toolkit Installer")]
[assembly: AssemblyProduct("PDF Master")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace PDFMasterSetup
{
    public class SetupForm : Form
    {
        private TextBox txtDir;
        private Button btnBrowse;
        private CheckBox chkDesktop;
        private CheckBox chkStartMenu;
        private CheckBox chkLaunch;
        private ProgressBar progressBar;
        private Label lblStatus;
        private Button btnInstall;
        private Button btnCancel;
        private bool finished = false;
        private string installedExePath = "";

        public SetupForm()
        {
            Text = "PDF Master 1.0.0 Setup";
            Size = new Size(560, 430);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(247, 248, 250);
            Font = new Font("Segoe UI", 9.5f, FontStyle.Regular);
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

            // Header Banner
            Panel header = new Panel
            {
                Dock = DockStyle.Top,
                Height = 84,
                BackColor = Color.FromArgb(229, 50, 45)
            };
            PictureBox picIcon = new PictureBox
            {
                Location = new Point(22, 16),
                Size = new Size(52, 52),
                SizeMode = PictureBoxSizeMode.Zoom,
                BackColor = Color.Transparent
            };
            try
            {
                Icon ico = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
                if (ico != null) picIcon.Image = ico.ToBitmap();
            }
            catch { }
            header.Controls.Add(picIcon);

            Label lblTitle = new Label
            {
                Text = "PDF Master – Offline PDF Toolkit",
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 15f, FontStyle.Bold),
                AutoSize = true,
                Location = new Point(86, 16),
                BackColor = Color.Transparent
            };
            Label lblSub = new Label
            {
                Text = "Fast, lightweight, 100% offline PDF tools for Windows 10 & 11",
                ForeColor = Color.FromArgb(254, 226, 226),
                Font = new Font("Segoe UI", 9.5f, FontStyle.Regular),
                AutoSize = true,
                Location = new Point(88, 48),
                BackColor = Color.Transparent
            };
            header.Controls.Add(lblTitle);
            header.Controls.Add(lblSub);
            Controls.Add(header);

            // Body
            Label lblDir = new Label
            {
                Text = "Destination folder:",
                Location = new Point(24, 104),
                AutoSize = true,
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold),
                ForeColor = Color.FromArgb(31, 35, 40)
            };
            Controls.Add(lblDir);

            string defaultDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs", "PDFMaster"
            );
            txtDir = new TextBox
            {
                Text = defaultDir,
                Location = new Point(24, 130),
                Size = new Size(400, 27)
            };
            Controls.Add(txtDir);

            btnBrowse = new Button
            {
                Text = "Browse...",
                Location = new Point(432, 128),
                Size = new Size(92, 29),
                BackColor = Color.White,
                FlatStyle = FlatStyle.System
            };
            btnBrowse.Click += OnBrowse;
            Controls.Add(btnBrowse);

            chkDesktop = new CheckBox
            {
                Text = "Create a Desktop shortcut",
                Checked = true,
                AutoSize = true,
                Location = new Point(26, 174)
            };
            chkStartMenu = new CheckBox
            {
                Text = "Create a Start Menu shortcut",
                Checked = true,
                AutoSize = true,
                Location = new Point(26, 202)
            };
            chkLaunch = new CheckBox
            {
                Text = "Launch PDF Master when installation completes",
                Checked = true,
                AutoSize = true,
                Location = new Point(26, 230)
            };
            Controls.Add(chkDesktop);
            Controls.Add(chkStartMenu);
            Controls.Add(chkLaunch);

            lblStatus = new Label
            {
                Text = "Ready to install PDF Master.",
                Location = new Point(24, 272),
                Size = new Size(500, 22),
                ForeColor = Color.FromArgb(90, 98, 112)
            };
            Controls.Add(lblStatus);

            progressBar = new ProgressBar
            {
                Location = new Point(24, 298),
                Size = new Size(500, 22),
                Minimum = 0,
                Maximum = 100,
                Value = 0
            };
            Controls.Add(progressBar);

            btnInstall = new Button
            {
                Text = "Install Now",
                Location = new Point(316, 342),
                Size = new Size(110, 34),
                BackColor = Color.FromArgb(229, 50, 45),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 9.5f, FontStyle.Bold)
            };
            btnInstall.FlatAppearance.BorderSize = 0;
            btnInstall.Click += OnInstallClicked;
            Controls.Add(btnInstall);

            btnCancel = new Button
            {
                Text = "Cancel",
                Location = new Point(434, 342),
                Size = new Size(90, 34),
                FlatStyle = FlatStyle.System
            };
            btnCancel.Click += (s, e) => Close();
            Controls.Add(btnCancel);
        }

        private void OnBrowse(object sender, EventArgs e)
        {
            using (var dlg = new FolderBrowserDialog())
            {
                dlg.Description = "Select destination folder for PDF Master";
                dlg.SelectedPath = txtDir.Text;
                if (dlg.ShowDialog(this) == DialogResult.OK)
                    txtDir.Text = dlg.SelectedPath;
            }
        }

        private void OnInstallClicked(object sender, EventArgs e)
        {
            if (finished)
            {
                if (chkLaunch.Checked && File.Exists(installedExePath))
                {
                    try { Process.Start(new ProcessStartInfo(installedExePath) { WorkingDirectory = Path.GetDirectoryName(installedExePath) }); }
                    catch { }
                }
                Close();
                return;
            }

            string targetDir = txtDir.Text.Trim();
            if (string.IsNullOrEmpty(targetDir))
            {
                MessageBox.Show(this, "Please select an installation folder.", "Setup", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            btnInstall.Enabled = false;
            btnBrowse.Enabled = false;
            txtDir.ReadOnly = true;
            chkDesktop.Enabled = false;
            chkStartMenu.Enabled = false;

            bool makeDesktop = chkDesktop.Checked;
            bool makeStart = chkStartMenu.Checked;

            Thread worker = new Thread(() =>
            {
                try
                {
                    InstallerEngine.RunInstall(targetDir, makeDesktop, makeStart, (pct, msg) =>
                    {
                        BeginInvoke((Action)(() =>
                        {
                            progressBar.Value = Math.Max(0, Math.Min(100, pct));
                            lblStatus.Text = msg;
                        }));
                    });

                    BeginInvoke((Action)(() =>
                    {
                        installedExePath = Path.Combine(targetDir, "PDFMaster.exe");
                        finished = true;
                        progressBar.Value = 100;
                        lblStatus.Text = "Installation complete! Click Finish to exit setup.";
                        lblStatus.ForeColor = Color.FromArgb(22, 121, 75);
                        btnInstall.Text = "Finish";
                        btnInstall.Enabled = true;
                        btnCancel.Enabled = false;
                    }));
                }
                catch (Exception ex)
                {
                    BeginInvoke((Action)(() =>
                    {
                        lblStatus.Text = "Installation failed: " + ex.Message;
                        lblStatus.ForeColor = Color.FromArgb(190, 30, 30);
                        MessageBox.Show(this, "Installation error:\n" + ex.Message, "PDF Master Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        btnInstall.Enabled = true;
                    }));
                }
            });
            worker.IsBackground = true;
            worker.Start();
        }
    }

    public static class InstallerEngine
    {
        public static void RunInstall(string targetDir, bool desktopShortcut, bool startMenuShortcut, Action<int, string> progress)
        {
            progress(5, "Preparing installation directory...");
            Directory.CreateDirectory(targetDir);

            using (Stream resStream = Assembly.GetExecutingAssembly().GetManifestResourceStream("PDFMaster.payload.zip"))
            {
                if (resStream == null)
                    throw new InvalidOperationException("Embedded payload archive was not found.");

                using (ZipArchive archive = new ZipArchive(resStream, ZipArchiveMode.Read))
                {
                    int total = Math.Max(1, archive.Entries.Count);
                    int count = 0;
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        count++;
                        string fullPath = Path.GetFullPath(Path.Combine(targetDir, entry.FullName));
                        if (!fullPath.StartsWith(Path.GetFullPath(targetDir), StringComparison.OrdinalIgnoreCase))
                            continue;

                        if (string.IsNullOrEmpty(entry.Name))
                        {
                            Directory.CreateDirectory(fullPath);
                            continue;
                        }

                        Directory.CreateDirectory(Path.GetDirectoryName(fullPath));
                        entry.ExtractToFile(fullPath, true);
                        if (count % 5 == 0 || count == total)
                        {
                            int pct = 10 + (int)(80.0 * count / total);
                            progress(pct, "Extracting: " + entry.Name);
                        }
                    }
                }
            }

            string exePath = Path.Combine(targetDir, "PDFMaster.exe");
            string uninstPath = Path.Combine(targetDir, "Uninstall.exe");

            if (desktopShortcut)
            {
                progress(92, "Creating Desktop shortcut...");
                string deskLnk = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "PDF Master.lnk");
                CreateShortcut(deskLnk, exePath, targetDir, "PDF Master - Offline PDF Toolkit");
            }

            if (startMenuShortcut)
            {
                progress(95, "Creating Start Menu shortcuts...");
                string smDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "PDF Master");
                Directory.CreateDirectory(smDir);
                CreateShortcut(Path.Combine(smDir, "PDF Master.lnk"), exePath, targetDir, "PDF Master - Offline PDF Toolkit");
                if (File.Exists(uninstPath))
                {
                    CreateShortcut(Path.Combine(smDir, "Uninstall PDF Master.lnk"), uninstPath, targetDir, "Uninstall PDF Master");
                }
            }

            progress(98, "Registering application in Windows...");
            RegisterUninstall(targetDir, exePath, uninstPath);
            progress(100, "Done.");
        }

        private static void CreateShortcut(string lnkPath, string targetPath, string workDir, string description)
        {
            try
            {
                Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                if (shellType == null) return;
                dynamic shell = Activator.CreateInstance(shellType);
                dynamic shortcut = shell.CreateShortcut(lnkPath);
                shortcut.TargetPath = targetPath;
                shortcut.WorkingDirectory = workDir;
                shortcut.Description = description;
                shortcut.IconLocation = targetPath + ",0";
                shortcut.Save();
            }
            catch { }
        }

        private static void RegisterUninstall(string targetDir, string exePath, string uninstPath)
        {
            try
            {
                using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\PDFMaster"))
                {
                    if (key != null)
                    {
                        key.SetValue("DisplayName", "PDF Master - Offline PDF Toolkit");
                        key.SetValue("DisplayVersion", "1.0.0");
                        key.SetValue("Publisher", "PDF Master");
                        key.SetValue("DisplayIcon", exePath);
                        key.SetValue("InstallLocation", targetDir);
                        key.SetValue("UninstallString", "\"" + uninstPath + "\"");
                        key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                        key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                    }
                }
            }
            catch { }
        }
    }

    static class Program
    {
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        [STAThread]
        static int Main(string[] args)
        {
            try { SetProcessDPIAware(); } catch { }

            bool silent = false;
            string customDir = null;
            bool noShortcuts = false;

            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                if (a.Equals("/S", StringComparison.OrdinalIgnoreCase) ||
                    a.Equals("/SILENT", StringComparison.OrdinalIgnoreCase) ||
                    a.Equals("/VERYSILENT", StringComparison.OrdinalIgnoreCase))
                {
                    silent = true;
                }
                else if (a.StartsWith("/DIR=", StringComparison.OrdinalIgnoreCase))
                {
                    customDir = a.Substring(5).Trim('"');
                }
                else if (a.Equals("/NOSHORTCUTS", StringComparison.OrdinalIgnoreCase))
                {
                    noShortcuts = true;
                }
            }

            if (silent)
            {
                string target = customDir ?? Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Programs", "PDFMaster"
                );
                InstallerEngine.RunInstall(target, !noShortcuts, !noShortcuts, (p, m) => { });
                return 0;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupForm());
            return 0;
        }
    }
}
"""


def find_csc() -> str:
    for p in CSC_PATHS:
        if os.path.isfile(p):
            return p
    raise RuntimeError("Windows .NET C# compiler (csc.exe) not found.")


def build_installer() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_app = os.path.join(root, "dist", "PDFMaster")
    if not os.path.isfile(os.path.join(dist_app, "PDFMaster.exe")):
        raise RuntimeError(f"dist\\PDFMaster\\PDFMaster.exe not found in {dist_app}. Run PyInstaller first.")

    csc = find_csc()
    ico_path = os.path.join(root, "resources", "icons", "app.ico")
    work_dir = os.path.join(root, "build", "installer_work")
    os.makedirs(work_dir, exist_ok=True)

    # 1. Compile Uninstall.exe and place it inside dist\PDFMaster
    uninst_cs = os.path.join(work_dir, "Uninstaller.cs")
    uninst_exe = os.path.join(dist_app, "Uninstall.exe")
    with open(uninst_cs, "w", encoding="utf-8") as f:
        f.write(UNINSTALLER_CS)

    cmd_uninst = [
        csc,
        "/nologo",
        "/target:winexe",
        "/optimize+",
        f"/out:{uninst_exe}",
        f"/win32icon:{ico_path}",
        "/r:System.dll",
        "/r:System.Windows.Forms.dll",
        uninst_cs,
    ]
    subprocess.run(cmd_uninst, check=True)

    # 2. Compress dist\PDFMaster/* into payload.zip
    payload_zip = os.path.join(work_dir, "payload.zip")
    if os.path.exists(payload_zip):
        os.remove(payload_zip)
    print("Compressing application payload into installer archive...")
    with zipfile.ZipFile(payload_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for dirpath, _dirnames, filenames in os.walk(dist_app):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, dist_app)
                zf.write(full, rel)

    # 3. Compile PDFMaster-Setup.exe with embedded payload.zip
    setup_cs = os.path.join(work_dir, "Setup.cs")
    with open(setup_cs, "w", encoding="utf-8") as f:
        f.write(SETUP_CS)

    out_installer_dir = os.path.join(root, "installer")
    os.makedirs(out_installer_dir, exist_ok=True)
    setup_exe_installer = os.path.join(out_installer_dir, "PDFMaster-Setup.exe")
    setup_exe_dist = os.path.join(root, "dist", "PDFMaster-Setup.exe")

    cmd_setup = [
        csc,
        "/nologo",
        "/target:winexe",
        "/optimize+",
        f"/out:{setup_exe_installer}",
        f"/win32icon:{ico_path}",
        f"/resource:{payload_zip},PDFMaster.payload.zip",
        "/r:System.dll",
        "/r:System.Drawing.dll",
        "/r:System.Windows.Forms.dll",
        "/r:System.IO.Compression.dll",
        "/r:System.IO.Compression.FileSystem.dll",
        "/r:Microsoft.CSharp.dll",
        setup_cs,
    ]
    subprocess.run(cmd_setup, check=True)
    shutil.copy2(setup_exe_installer, setup_exe_dist)
    shutil.copy2(uninst_exe, os.path.join(out_installer_dir, "Uninstall.exe"))
    if os.path.isfile(os.path.join(root, "installer.iss")):
        shutil.copy2(os.path.join(root, "installer.iss"), os.path.join(out_installer_dir, "installer.iss"))
    size_mb = os.path.getsize(setup_exe_installer) / (1024 * 1024)
    print(f"Built installer: {setup_exe_installer} ({size_mb:.1f} MB)")
    return setup_exe_installer


if __name__ == "__main__":
    build_installer()
