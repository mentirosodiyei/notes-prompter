use framework "Foundation"
use scripting additions
if not (application id "com.microsoft.Powerpoint" is running) then return "{}"
with timeout of 2 seconds
    tell application id "com.microsoft.Powerpoint"
        if (count of presentations) is 0 then return "{}"
        if (count of slide show windows) > 0 then
            set showWindow to slide show window 1
            set currentDeck to presentation of showWindow
            set currentSlide to slide of slideshow view of showWindow
        else
            set currentDeck to active presentation
            set currentSlide to slide of view of active window
        end if
        set slideIndex to slide index of currentSlide
        set slideTotal to count of slides of currentDeck
        set deckName to name of currentDeck
        set deckPath to full name of currentDeck
        set noteText to ""
        repeat with noteShape in (get shapes of notes page of currentSlide)
            if class of noteShape is place holder then
                if placeholder type of noteShape is placeholder type body placeholder then
                    set noteText to content of text range of text frame of noteShape
                    exit repeat
                end if
            end if
        end repeat
    end tell
end timeout
set payload to current application's NSDictionary's dictionaryWithObjects:{deckName, deckPath, slideIndex, slideTotal, noteText} forKeys:{"name", "path", "index", "total", "notes"}
set jsonData to current application's NSJSONSerialization's dataWithJSONObject:payload options:0 |error|:(missing value)
return (current application's NSString's alloc()'s initWithData:jsonData encoding:(current application's NSUTF8StringEncoding)) as text
