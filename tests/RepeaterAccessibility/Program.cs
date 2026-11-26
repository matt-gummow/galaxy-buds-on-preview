using Avalonia;
using Avalonia.Automation.Peers;
using Avalonia.Controls;
using Avalonia.Controls.Templates;
using Avalonia.Headless;
using Avalonia.Threading;
using FluentAvalonia.UI.Controls;

AppBuilder.Configure<Application>()
    .UseHeadless(new AvaloniaHeadlessPlatformOptions())
    .SetupWithoutStarting();

var repeater = new FAItemsRepeater
{
    Layout = new FAStackLayout(),
    ItemTemplate = new FuncDataTemplate<string>((value, _) => new Button { Content = value, Width = 120, Height = 36 })
};
var peer = ControlAutomationPeer.CreatePeerForElement(repeater);
if (peer.GetChildren().Count != 0)
    throw new InvalidOperationException("An empty repeater reported children.");

var window = new Window { Width = 400, Height = 300, Content = repeater };
repeater.ItemsSource = new[] { "First", "Second" };
window.Show();
Dispatcher.UIThread.RunJobs();
repeater.Measure(new Size(400, 300));
repeater.Arrange(new Rect(0, 0, 400, 300));
if (peer.GetChildren().Count != 2)
    throw new InvalidOperationException("A populated repeater lost its accessible items.");

repeater.ItemsSource = Array.Empty<string>();
Dispatcher.UIThread.RunJobs();
repeater.Measure(new Size(400, 300));
repeater.Arrange(new Rect(0, 0, 400, 300));
if (peer.GetChildren().Count != 0)
    throw new InvalidOperationException("A cleared repeater retained accessible items.");
window.Close();
Console.WriteLine("Passed empty, populated and cleared repeater accessibility checks.");
