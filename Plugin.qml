import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons

Item {
    id: root
    property var shell: null
    property var manifest: null
    property bool opened: false
    property var status: ({})
    property string statusError: ""
    readonly property string pluginDirectory: decodeURIComponent(Qt.resolvedUrl(".").toString().replace(/^file:\/\//, ""))

    function refresh() {
        if (!statusProcess.running) {
            statusError = ""
            statusProcess.running = true
        }
    }
    function open(_payload) {
        opened = true
        refresh()
        Qt.callLater(function() { content.forceActiveFocus() })
    }
    function close() { opened = false }
    function toggle() { if (opened) close(); else open("{}") }
    function setup(action) {
        var args = ["omarchy", "launch", "terminal", "python3", pluginDirectory + "tools/plugin_setup.py", action]
        if (dictation.checked && action !== "uninstall") args.push("--with-dictation")
        if (karaoke.checked && action !== "uninstall") args.push("--with-karaoke")
        if (karaoke.checked && background.checked && action !== "uninstall") args.push("--with-background")
        Quickshell.execDetached(args)
        close()
    }

    Process {
        id: statusProcess
        command: ["python3", root.pluginDirectory + "tools/plugin_status.py"]
        stdout: StdioCollector {
            onStreamFinished: {
                try { root.status = JSON.parse(text) }
                catch (_error) { root.statusError = "Could not read status. Open the README for troubleshooting." }
            }
        }
        onExited: function(exitCode) {
            if (exitCode !== 0) root.statusError = "Status check failed. Confirm Python 3 and systemd are installed."
        }
    }

    PanelWindow {
        id: window
        visible: root.opened
        anchors { top: true; bottom: true; left: true; right: true }
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.namespace: "touchbar-radio-setup"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

        Rectangle { anchors.fill: parent; color: Color.menu.scrim }
        MouseArea { anchors.fill: parent; onClicked: root.close() }
        Rectangle {
            id: card
            anchors.centerIn: parent
            width: Math.min(640, window.width - 32)
            height: Math.min(content.implicitHeight + 48, window.height - 32)
            color: Color.menu.background
            border.color: Color.menu.border
            radius: 12
            MouseArea { anchors.fill: parent }
            Flickable {
                anchors.fill: parent
                anchors.margins: 24
                contentHeight: content.implicitHeight
                clip: true
                Column {
                    id: content
                    width: parent.width
                    spacing: 14
                    focus: true
                    Keys.onEscapePressed: root.close()
                    Text {
                        width: parent.width
                        text: "Touch Bar Radio"
                        color: Color.menu.text
                        font.pixelSize: 24
                        font.bold: true
                    }
                    Text {
                        width: parent.width
                        text: "Radio Atlas on your T2 MacBook Touch Bar. Setup requires a working tiny-dfr display and Omarchy with Hyprland Lua."
                        color: Color.menu.text
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        textFormat: Text.PlainText
                        text: root.statusError || (statusProcess.running ? "Checking services…" :
                            "Touch Bar: " + (root.status.tinyDfr || "unknown") +
                            "\nRenderer: " + (root.status.renderer || "unknown") +
                            "\nMetadata: " + (root.status.feed || "unknown") +
                            "\nGestures: " + (root.status.gestures || "unknown") +
                            "\nKaraoke: " + (root.status.karaoke || "not installed") +
                            "\nRadio Atlas: " + (root.status.radioAtlas ? "found" : "not found") +
                            "\nHyprland Lua: " + (root.status.hyprlandLua ? "found" : "not found"))
                        color: Color.menu.text
                        wrapMode: Text.WordWrap
                    }
                    CheckBox {
                        id: karaoke
                        text: "Enable song recognition and timed lyrics"
                        palette.windowText: Color.menu.text
                    }
                    CheckBox {
                        id: background
                        enabled: karaoke.checked
                        text: "Include Wikipedia song and artist background"
                        palette.windowText: Color.menu.text
                    }
                    Text {
                        width: parent.width
                        visible: karaoke.checked
                        text: "Requires the Python 3.12 environment described in the README. Recognition sends a short sample of radio audio to Shazam and song names to LRCLIB. Background lookup also sends names to Wikipedia."
                        color: Color.menu.text
                        wrapMode: Text.WordWrap
                    }
                    CheckBox {
                        id: dictation
                        text: "Include Voxtype dictation button"
                        palette.windowText: Color.menu.text
                    }
                    Text {
                        width: parent.width
                        text: "Setup opens a terminal for confirmation and administrator authentication. It installs services and input permissions, backs up tiny-dfr configuration, and adds keybindings. Preview lists planned files without changing them."
                        color: Color.menu.text
                        wrapMode: Text.WordWrap
                    }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Button { text: "Preview setup"; onClicked: root.setup("preview") }
                        Button { text: "Install hardware support"; onClicked: root.setup("install") }
                        Button { text: "Uninstall hardware support"; onClicked: root.setup("uninstall") }
                    }
                    Text {
                        width: parent.width
                        text: "Before removing this plugin, uninstall hardware support here. Disabling or removing the panel leaves the separately installed Touch Bar services running."
                        color: Color.menu.text
                        wrapMode: Text.WordWrap
                    }
                    Flow {
                        width: parent.width
                        spacing: 8
                        Button { text: "Refresh"; enabled: !statusProcess.running; onClicked: root.refresh() }
                        Button { text: "README"; onClicked: Qt.openUrlExternally("https://github.com/tonybo/omarchy-touchbar-radio#readme") }
                        Button { text: "Close"; onClicked: root.close() }
                    }
                }
            }
        }
    }
}
