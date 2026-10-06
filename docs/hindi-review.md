# Hindi interface text: review sheet

Generated on 2026-10-01 from `web/src/i18n/hi.ts` and `web/src/i18n/en.ts`. **Nothing in `hi.ts` has been changed.**
It covers every Hindi string: 234 in total, **37 new in the Phase 10 redesign** (marked **NEW**).

How to use it:
- Fill in the **Your correction** column, or send changes as `current text -> new text`.
- Keep `{placeholders}` such as `{date}`, `{n}`, `{max}`, `{seconds}` exactly as they are; the app fills them in.
  A test checks that Hindi and English use the same placeholders.
- Brand and model names (WhatsApp, KYC, OTP, Groq, Gemini, TF-IDF, DistilBERT, ...) and all numbers are kept as in
  English on purpose. The About-page numbers come from results.md, and a test checks that the Hindi findings keep the
  same numbers.
- ⏎ marks a line break inside a diagram box.
- **Not shown**: defined but not currently displayed anywhere in the interface. Low priority.
- Analysis results (warning signs, explanation, advice) are not in this file: they come from the API in the
  message's own language.


## Page title

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 1 | `meta.title` |  | Scam Message Checker | स्कैम मैसेज जाँच |  |
| 2 | `meta.description` |  | Check an SMS, WhatsApp or email message - or a screenshot - for scam and phishing signs. | किसी SMS, WhatsApp या ईमेल मैसेज - या स्क्रीनशॉट - में स्कैम और फ़िशिंग के संकेत जाँचें। |  |

## Navigation

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 3 | `nav.label` |  | Main | मुख्य |  |
| 4 | `nav.analyze` |  | Check a message | मैसेज जाँचें |  |
| 5 | `nav.about` |  | How it works | यह कैसे काम करता है |  |
| 6 | `nav.skip` |  | Skip to main content | मुख्य सामग्री पर जाएँ |  |

## Language switch

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 7 | `langSwitch.label` |  | Interface language | इंटरफ़ेस की भाषा |  |
| 8 | `langSwitch.en` |  | EN | EN |  |
| 9 | `langSwitch.hi` |  | हिंदी | हिंदी |  |

## Theme switch

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 10 | `theme.label` | **NEW** | Colour theme | रंग की थीम |  |
| 11 | `theme.system` | **NEW** | System | सिस्टम |  |
| 12 | `theme.light` | **NEW** | Light | हल्की |  |
| 13 | `theme.dark` | **NEW** | Dark | गहरी |  |

## Hero (top of the Check page)

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 14 | `hero.eyebrow` | **NEW** | Scam & phishing checker | स्कैम और फ़िशिंग जाँच |  |
| 15 | `hero.title` | **NEW** | Is this message a scam? | क्या यह मैसेज स्कैम है? |  |
| 16 | `hero.subtitle` | **NEW** | Paste an SMS, WhatsApp or email message, or drop a screenshot. You get a clear risk level, the warning signs and what to do, in English, Hindi or Hinglish. | SMS, WhatsApp या ईमेल मैसेज पेस्ट करें, या स्क्रीनशॉट डालें। आपको साफ़ जोखिम स्तर, चेतावनी के संकेत और आगे क्या करना है, यह अंग्रेज़ी, हिंदी या हिंग्लिश में बताया जाएगा। |  |
| 17 | `hero.points.1` | **NEW** | Verdict from fixed rules, never from the AI | निष्कर्ष तय नियमों से, AI से कभी नहीं |  |
| 18 | `hero.points.2` | **NEW** | Links, numbers and codes masked before any AI sees the text | किसी भी AI के देखने से पहले लिंक, नंबर और कोड छिपा दिए जाते हैं |  |
| 19 | `hero.points.3` | **NEW** | No message text is stored | मैसेज का कोई टेक्स्ट सेव नहीं होता |  |

## Privacy dialog

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 20 | `privacyDialog.trigger` | **NEW** | What happens to my message? | मेरे मैसेज का क्या होता है? |  |
| 21 | `privacyDialog.title` | **NEW** | What happens to your message | आपके मैसेज का क्या होता है |  |
| 22 | `privacyDialog.description` | **NEW** | A short summary. The full details are on the How it works page. | एक छोटा सार। पूरी जानकारी "यह कैसे काम करता है" पेज पर है। |  |
| 23 | `privacyDialog.more` | **NEW** | Read how it works | यह कैसे काम करता है, पढ़ें |  |
| 24 | `privacyDialog.close` | **NEW** | Close | बंद करें |  |

## Empty result area

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 25 | `empty.title` | **NEW** | Your result will appear here | आपका नतीजा यहाँ दिखेगा |  |
| 26 | `empty.body` | **NEW** | Paste a message above, or try one of the samples below. | ऊपर कोई मैसेज पेस्ट करें, या नीचे दिया कोई सैंपल आज़माएँ। |  |

## Demo-mode banner

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 27 | `mode.checking` |  | Connecting to the analysis server… | जाँच सर्वर से जुड़ रहे हैं… |  |
| 28 | `mode.demoBadge` |  | Demo mode | डेमो मोड |  |
| 29 | `mode.notHostedTitle` |  | Demo mode: the live backend is not hosted yet | डेमो मोड: लाइव बैकएंड अभी होस्ट नहीं किया गया है |  |
| 30 | `mode.notHostedBody` |  | The live backend is not hosted yet, so this site shows real results that were recorded from the actual system on {date}, for the sample messages below only. Checking your own messages will work once the backend is hosted. | लाइव बैकएंड अभी होस्ट नहीं किया गया है, इसलिए यह साइट असली सिस्टम से {date} को रिकॉर्ड किए गए असली नतीजे दिखाती है, केवल नीचे दिए गए सैंपल मैसेज के लिए। बैकएंड होस्ट होने के बाद आप अपने मैसेज भी जाँच सकेंगे। |  |
| 31 | `mode.unreachableTitle` |  | Demo mode: the server is unreachable | डेमो मोड: सर्वर तक नहीं पहुँच पा रहे हैं |  |
| 32 | `mode.unreachableBody` |  | It may be asleep or starting up. Meanwhile, this site shows real responses recorded on {date}, for the sample messages below only. | हो सकता है सर्वर सो रहा हो या शुरू हो रहा हो। तब तक यह साइट {date} को रिकॉर्ड किए गए असली जवाब दिखाती है, केवल नीचे दिए गए सैंपल मैसेज के लिए। |  |
| 33 | `mode.retry` |  | Try the live server again | लाइव सर्वर फिर से आज़माएँ |  |
| 34 | `mode.retrying` |  | Checking… | जाँच रहे हैं… |  |
| 35 | `mode.stillUnreachable` |  | Still unreachable. Try again in a minute. | सर्वर तक अब भी नहीं पहुँच पा रहे हैं। एक मिनट बाद फिर कोशिश करें। |  |
| 36 | `mode.nowLive` |  | The live server is back. You can check your own messages now. | लाइव सर्वर वापस आ गया है। अब आप अपने मैसेज जाँच सकते हैं। |  |

## Input card

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 37 | `form.heading` |  | Check a message | मैसेज जाँचें |  |
| 38 | `form.intro` |  | Paste a suspicious message or upload a screenshot. You'll get a risk level, the warning signs, and what to do. | कोई संदिग्ध मैसेज पेस्ट करें या स्क्रीनशॉट अपलोड करें। आपको जोखिम का स्तर, चेतावनी के संकेत और आगे क्या करना है, यह बताया जाएगा। |  |
| 39 | `form.tabsLabel` |  | What do you want to check? | आप क्या जाँचना चाहते हैं? |  |
| 40 | `form.tabText` |  | Text | टेक्स्ट |  |
| 41 | `form.tabImage` |  | Screenshot | स्क्रीनशॉट |  |
| 42 | `form.textLabel` |  | Message text | मैसेज का टेक्स्ट |  |
| 43 | `form.textPlaceholder` |  | Paste the SMS, WhatsApp or email message here… | SMS, WhatsApp या ईमेल मैसेज यहाँ पेस्ट करें… |  |
| 44 | `form.charCount` |  | {n} / {max} characters | {n} / {max} अक्षर |  |
| 45 | `form.imageLabel` |  | Screenshot of the message | मैसेज का स्क्रीनशॉट |  |
| 46 | `form.dropHint` |  | Drag a screenshot here, or choose a file. PNG, JPEG or WebP, up to 5 MB. | स्क्रीनशॉट यहाँ खींचकर छोड़ें, या फ़ाइल चुनें। PNG, JPEG या WebP, 5 MB तक। |  |
| 47 | `form.chooseFile` |  | Choose a screenshot | स्क्रीनशॉट चुनें |  |
| 48 | `form.removeImage` |  | Remove screenshot | स्क्रीनशॉट हटाएँ |  |
| 49 | `form.previewAlt` |  | Preview of the screenshot you selected | आपके चुने हुए स्क्रीनशॉट का प्रीव्यू |  |
| 50 | `form.selectedFile` |  | Selected: {name} | चुनी गई फ़ाइल: {name} |  |
| 51 | `form.dropActive` | **NEW** | Drop the screenshot to add it | स्क्रीनशॉट जोड़ने के लिए यहाँ छोड़ें |  |
| 52 | `form.viewFullSize` | **NEW** | View full size | पूरे आकार में देखें |  |
| 53 | `form.fullSizeTitle` | **NEW** | Your screenshot | आपका स्क्रीनशॉट |  |
| 54 | `form.submit` |  | Check message | मैसेज जाँचें |  |
| 55 | `form.submitImage` |  | Check screenshot | स्क्रीनशॉट जाँचें |  |
| 56 | `form.analyzingText` |  | Checking the message… | मैसेज जाँचा जा रहा है… |  |
| 57 | `form.analyzingImage` |  | Reading the screenshot… usually about 5 seconds. | स्क्रीनशॉट पढ़ा जा रहा है… आमतौर पर लगभग 5 सेकंड लगते हैं। |  |
| 58 | `form.demoDisabled` |  | In demo mode only the samples below can be shown. Checking new messages needs the live server. | डेमो मोड में केवल नीचे दिए गए सैंपल दिखाए जा सकते हैं। नए मैसेज जाँचने के लिए लाइव सर्वर चाहिए। |  |
| 59 | `form.privacyHint` |  | Don't paste passwords or full card numbers. Links, phone numbers and codes are masked before any AI sees the text. | पासवर्ड या पूरा कार्ड नंबर पेस्ट न करें। किसी भी AI के टेक्स्ट देखने से पहले लिंक, फ़ोन नंबर और कोड छिपा दिए जाते हैं। |  |

## Samples

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 60 | `samples.heading` |  | Try a sample | कोई सैंपल आज़माएँ |  |
| 61 | `samples.intro` |  | Click a sample to check it. | जाँचने के लिए किसी सैंपल पर क्लिक करें। |  |
| 62 | `samples.textHeading` |  | Sample messages | सैंपल मैसेज |  |
| 63 | `samples.imageHeading` |  | Sample screenshots | सैंपल स्क्रीनशॉट |  |
| 64 | `samples.expectedScam` |  | Written as a scam | स्कैम के रूप में लिखा गया |  |
| 65 | `samples.expectedSafe` |  | Written as safe | सुरक्षित के रूप में लिखा गया |  |
| 66 | `samples.screenshotAlt` |  | Sample screenshot: {title} | सैंपल स्क्रीनशॉट: {title} |  |
| 67 | `samples.titles.enKycLink` |  | English - fake KYC update with a link | अंग्रेज़ी - लिंक के साथ नकली KYC अपडेट |  |
| 68 | `samples.titles.enOtpCall` |  | English - asks you to read out a code (no link) | अंग्रेज़ी - कोड पढ़कर सुनाने को कहता है (कोई लिंक नहीं) |  |
| 69 | `samples.titles.hinglishBijliLink` |  | Hinglish - electricity cut-off threat with a link | हिंग्लिश - लिंक के साथ बिजली कटने की धमकी |  |
| 70 | `samples.titles.hinglishLottery` |  | Hinglish - lottery prize, asks for bank details | हिंग्लिश - लॉटरी इनाम, बैंक डिटेल्स माँगता है |  |
| 71 | `samples.titles.enLunch` |  | English - friend asking about lunch | अंग्रेज़ी - दोस्त लंच के बारे में पूछ रहा है |  |
| 72 | `samples.titles.hinglishViOffer` |  | Hinglish - telecom recharge offer with the real website | हिंग्लिश - असली वेबसाइट के साथ रिचार्ज ऑफ़र |  |
| 73 | `samples.titles.hindiKycLink` |  | Hindi - fake KYC update with a link | हिंदी - लिंक के साथ नकली KYC अपडेट |  |
| 74 | `samples.titles.shotSmsKyc` |  | SMS screenshot - fake KYC update | SMS स्क्रीनशॉट - नकली KYC अपडेट |  |
| 75 | `samples.titles.shotWhatsappLottery` |  | WhatsApp screenshot - Hinglish lottery scam | WhatsApp स्क्रीनशॉट - हिंग्लिश लॉटरी स्कैम |  |
| 76 | `samples.titles.shotSmsLunch` |  | SMS screenshot - lunch plans | SMS स्क्रीनशॉट - लंच का प्लान |  |
| 77 | `samples.titles.shotDarkParcel` |  | WhatsApp dark mode - parcel fee scam | WhatsApp डार्क मोड - पार्सल फ़ीस स्कैम |  |
| 78 | `samples.titles.shotHindiKyc` |  | SMS screenshot in Hindi - fake KYC update | हिंदी में SMS स्क्रीनशॉट - नकली KYC अपडेट |  |

## Result card

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 79 | `result.heading` |  | Result | नतीजा |  |
| 80 | `result.demoTag` |  | Recorded demo result: real system output, recorded {date} | रिकॉर्ड किया गया डेमो नतीजा: असली सिस्टम का आउटपुट, {date} को रिकॉर्ड किया गया |  |
| 81 | `result.verdict.safe` |  | Looks safe | सुरक्षित लगता है |  |
| 82 | `result.verdict.suspicious` |  | Suspicious | संदिग्ध |  |
| 83 | `result.verdict.scam` |  | Likely scam | संभवतः स्कैम |  |
| 84 | `result.risk.low` |  | Low risk | कम जोखिम |  |
| 85 | `result.risk.medium` |  | Medium risk | मध्यम जोखिम |  |
| 86 | `result.risk.high` |  | High risk | उच्च जोखिम |  |
| 87 | `result.redFlags` |  | Warning signs | चेतावनी के संकेत |  |
| 88 | `result.noRedFlags` |  | No specific warning signs found. | कोई खास चेतावनी संकेत नहीं मिला। |  |
| 89 | `result.explanation` |  | Why | क्यों |  |
| 90 | `result.whatToDo` |  | What to do | क्या करें |  |
| 91 | `result.matchedPattern` |  | Closest known pattern | सबसे मिलता-जुलता जाना-पहचाना पैटर्न |  |
| 92 | `result.patternScam` |  | a known scam type | एक जाना-पहचाना स्कैम |  |
| 93 | `result.patternLegit` |  | a type of genuine message | एक तरह का असली मैसेज |  |
| 94 | `result.links` |  | Links in the message | मैसेज में मौजूद लिंक |  |
| 95 | `result.linkNote` |  | Shown defanged (hxxp, [.]) and deliberately not clickable. Don't open these links. | सुरक्षित रूप में (hxxp, [.]) दिखाए गए हैं और जानबूझकर क्लिक करने लायक नहीं हैं। इन लिंक को न खोलें। |  |
| 96 | `result.linkRisk` |  | Link risk: {risk} | लिंक का जोखिम: {risk} |  |
| 97 | `result.extractedText` |  | Text read from the screenshot | स्क्रीनशॉट से पढ़ा गया टेक्स्ट |  |
| 98 | `result.ocrQuality` |  | Reading quality | पढ़ने की गुणवत्ता |  |
| 99 | `result.ocrQualityValue.good` |  | Good | अच्छी |  |
| 100 | `result.ocrQualityValue.fair` |  | Fair - some words may be misread | ठीक-ठाक - कुछ शब्द गलत पढ़े जा सकते हैं |  |
| 101 | `result.ocrQualityValue.poor` |  | Poor - check the text below | कमज़ोर - नीचे दिया टेक्स्ट जाँच लें |  |
| 102 | `result.darkMode` |  | Dark-mode screenshot detected | डार्क मोड स्क्रीनशॉट पहचाना गया |  |
| 103 | `result.explainedBy` |  | Explanation written by {who}. | व्याख्या {who} लिखी गई। |  |
| 104 | `result.explainer.groq` |  | an AI model (Groq) | एक AI मॉडल (Groq) द्वारा |  |
| 105 | `result.explainer.gemini` |  | an AI model (Gemini) | एक AI मॉडल (Gemini) द्वारा |  |
| 106 | `result.explainer.template` |  | fixed templates (AI unavailable) | तय टेम्पलेट से (AI उपलब्ध नहीं) |  |
| 107 | `result.verdictNote` |  | The verdict and risk level come from the classifier and link checks, never from the AI. | निष्कर्ष और जोखिम का स्तर क्लासिफ़ायर और लिंक जाँच से तय होते हैं, AI से कभी नहीं। |  |
| 108 | `result.contentLangNote` | Not shown | The explanation is in the message's language. | व्याख्या मैसेज की भाषा में है। |  |
| 109 | `result.gaugeLabel` | **NEW** | Risk level: {risk} | जोखिम का स्तर: {risk} |  |
| 110 | `result.gaugeBand.low` | **NEW** | Low | कम |  |
| 111 | `result.gaugeBand.medium` | **NEW** | Medium | मध्यम |  |
| 112 | `result.gaugeBand.high` | **NEW** | High | उच्च |  |
| 113 | `result.inspectedLink` | **NEW** | Inspected link | जाँचा गया लिंक |  |
| 114 | `result.notClickable` | **NEW** | Not clickable | क्लिक करने लायक नहीं |  |
| 115 | `result.linkChecks` | **NEW** | Link checks ({n}) | लिंक की जाँचें ({n}) |  |
| 116 | `result.aiBadge` | **NEW**, Not shown | AI explanation | AI व्याख्या |  |
| 117 | `result.aiTooltip` | **NEW** | An AI wrote this explanation. The verdict and risk level come from the classifier and link checks, and the AI can't change them. | यह व्याख्या एक AI ने लिखी है। निष्कर्ष और जोखिम का स्तर क्लासिफ़ायर और लिंक जाँच से तय होते हैं, और AI इन्हें बदल नहीं सकता। |  |

## Feedback

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 118 | `feedback.question` |  | Was this correct? | क्या यह सही था? |  |
| 119 | `feedback.yes` |  | Yes | हाँ |  |
| 120 | `feedback.no` |  | No | नहीं |  |
| 121 | `feedback.sending` |  | Sending… | भेज रहे हैं… |  |
| 122 | `feedback.thanks` |  | Thanks - your answer was saved. No message text is stored. | धन्यवाद - आपका जवाब सेव हो गया। मैसेज का कोई भी टेक्स्ट सेव नहीं किया जाता। |  |
| 123 | `feedback.retry` |  | Your answer wasn't sent. You can try again. | आपका जवाब नहीं भेजा जा सका। आप फिर से कोशिश कर सकते हैं। |  |
| 124 | `feedback.toastSaved` | **NEW** | Feedback sent | फ़ीडबैक भेज दिया गया |  |
| 125 | `feedback.toastFailed` | **NEW** | Feedback not sent | फ़ीडबैक नहीं भेजा गया |  |

## Error messages

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 126 | `errors.heading` |  | Couldn't check that | इसे जाँचा नहीं जा सका |  |
| 127 | `errors.requestId` |  | Reference: {id} | संदर्भ: {id} |  |
| 128 | `errors.empty_text` |  | Please paste a message first. | कृपया पहले कोई मैसेज पेस्ट करें। |  |
| 129 | `errors.text_too_long` |  | That message is too long - please keep it under {max} characters. | यह मैसेज बहुत लंबा है - कृपया इसे {max} अक्षरों से कम रखें। |  |
| 130 | `errors.body_too_large` |  | That upload is too large. Screenshots must be under 5 MB. | यह अपलोड बहुत बड़ा है। स्क्रीनशॉट 5 MB से छोटा होना चाहिए। |  |
| 131 | `errors.too_large` |  | That screenshot is larger than 5 MB. Try cropping it or saving it as JPEG. | यह स्क्रीनशॉट 5 MB से बड़ा है। इसे क्रॉप करके या JPEG में सेव करके आज़माएँ। |  |
| 132 | `errors.unsupported_type` |  | Please upload a PNG, JPEG or WebP image. | कृपया PNG, JPEG या WebP इमेज अपलोड करें। |  |
| 133 | `errors.corrupt` |  | That image couldn't be opened. Try taking the screenshot again. | यह इमेज खुल नहीं पाई। स्क्रीनशॉट दोबारा लेकर आज़माएँ। |  |
| 134 | `errors.empty` |  | That file is empty. | यह फ़ाइल खाली है। |  |
| 135 | `errors.too_small` |  | That image is too small to read. | यह इमेज पढ़ने के लिए बहुत छोटी है। |  |
| 136 | `errors.too_many_pixels` |  | That image has too many pixels. Try a normal phone screenshot. | इस इमेज में बहुत ज़्यादा पिक्सल हैं। फ़ोन का सामान्य स्क्रीनशॉट आज़माएँ। |  |
| 137 | `errors.no_text_found` |  | No readable text was found in that screenshot. Try a clearer or larger one, or paste the text. | इस स्क्रीनशॉट में पढ़ने लायक कोई टेक्स्ट नहीं मिला। ज़्यादा साफ़ या बड़ा स्क्रीनशॉट आज़माएँ, या टेक्स्ट पेस्ट करें। |  |
| 138 | `errors.invalid_request` |  | Something about the request wasn't right. Please try again. | अनुरोध में कुछ गड़बड़ थी। कृपया फिर से कोशिश करें। |  |
| 139 | `errors.length_required` |  | Your browser sent an incomplete request. Please try again or use another browser. | आपके ब्राउज़र ने अधूरा अनुरोध भेजा। कृपया फिर से कोशिश करें या कोई दूसरा ब्राउज़र इस्तेमाल करें। |  |
| 140 | `errors.rate_limited` |  | Too many checks in a short time. Please wait {seconds} seconds and try again. | कम समय में बहुत ज़्यादा जाँचें हो गईं। कृपया {seconds} सेकंड रुककर फिर कोशिश करें। |  |
| 141 | `errors.rate_limited_generic` |  | Too many checks in a short time. Please wait a minute and try again. | कम समय में बहुत ज़्यादा जाँचें हो गईं। कृपया एक मिनट रुककर फिर कोशिश करें। |  |
| 142 | `errors.busy` |  | The server is busy right now. Please try again in a few seconds. | सर्वर अभी व्यस्त है। कृपया कुछ सेकंड बाद फिर कोशिश करें। |  |
| 143 | `errors.timeout` |  | The check took too long. Please try again. | जाँच में बहुत समय लग गया। कृपया फिर से कोशिश करें। |  |
| 144 | `errors.client_timeout` |  | The server didn't answer in time. It may be waking up - please try again in a minute. | सर्वर ने समय पर जवाब नहीं दिया। हो सकता है वह शुरू हो रहा हो - कृपया एक मिनट बाद फिर कोशिश करें। |  |
| 145 | `errors.classifier_unavailable` |  | The analysis model isn't available right now. Please try again later. | जाँच मॉडल अभी उपलब्ध नहीं है। कृपया बाद में कोशिश करें। |  |
| 146 | `errors.ocr_unavailable` |  | Screenshot reading isn't available right now. You can paste the text instead. | स्क्रीनशॉट पढ़ने की सुविधा अभी उपलब्ध नहीं है। आप टेक्स्ट पेस्ट कर सकते हैं। |  |
| 147 | `errors.feedback_not_configured` |  | Feedback isn't available right now. | फ़ीडबैक अभी उपलब्ध नहीं है। |  |
| 148 | `errors.feedback_storage_error` |  | Your feedback couldn't be saved right now. Please try again later. | आपका फ़ीडबैक अभी सेव नहीं हो पाया। कृपया बाद में कोशिश करें। |  |
| 149 | `errors.unknown_prediction` |  | This result is too old to rate, because the server restarted. | यह नतीजा रेट करने के लिए बहुत पुराना है, क्योंकि सर्वर दोबारा शुरू हो चुका है। |  |
| 150 | `errors.internal_error` |  | Something went wrong on the server. Please try again. | सर्वर पर कुछ गड़बड़ हुई। कृपया फिर से कोशिश करें। |  |
| 151 | `errors.network_error` |  | Couldn't reach the server. Check your connection and try again. | सर्वर तक नहीं पहुँच पाए। अपना इंटरनेट कनेक्शन जाँचकर फिर कोशिश करें। |  |
| 152 | `errors.not_configured` |  | No analysis server is configured for this site. | इस साइट के लिए कोई जाँच सर्वर सेट नहीं है। |  |
| 153 | `errors.unknown_error` |  | Something went wrong. Please try again. | कुछ गड़बड़ हो गई। कृपया फिर से कोशिश करें। |  |
| 154 | `errors.demo_unavailable` |  | That isn't one of the recorded samples, so it can't be shown in demo mode. | यह रिकॉर्ड किए गए सैंपल में से नहीं है, इसलिए इसे डेमो मोड में नहीं दिखाया जा सकता। |  |

## About page (How it works)

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 155 | `about.title` |  | How it works | यह कैसे काम करता है |  |
| 156 | `about.intro` |  | A portfolio project that checks SMS, WhatsApp and email messages (English, Hindi and Hinglish) for scam and phishing signs, and explains the result in plain language. | एक पोर्टफ़ोलियो प्रोजेक्ट जो SMS, WhatsApp और ईमेल मैसेज (अंग्रेज़ी, हिंदी और हिंग्लिश) में स्कैम और फ़िशिंग के संकेत जाँचता है और नतीजे को आसान भाषा में समझाता है। |  |
| 157 | `about.howHeading` |  | The pipeline | जाँच की प्रक्रिया |  |
| 158 | `about.diagramTitle` |  | Analysis pipeline | जाँच की प्रक्रिया का चित्र |  |
| 159 | `about.diagramDesc` |  | A screenshot is first read with OCR. The text is cleaned and links, phone numbers and one-time codes are masked. Three checks then run: a text classifier, a link analyzer and a search of known scam patterns. Fixed rules combine them into the verdict and risk level. An AI model only writes the explanation, with a template fallback. | स्क्रीनशॉट पहले OCR से पढ़ा जाता है। टेक्स्ट साफ़ किया जाता है और लिंक, फ़ोन नंबर और वन-टाइम कोड छिपा दिए जाते हैं। फिर तीन जाँचें होती हैं: टेक्स्ट क्लासिफ़ायर, लिंक जाँच और जाने-पहचाने स्कैम पैटर्न की खोज। तय नियम इन्हें मिलाकर निष्कर्ष और जोखिम का स्तर देते हैं। AI मॉडल केवल व्याख्या लिखता है; AI न हो तो टेम्पलेट इस्तेमाल होते हैं। |  |
| 160 | `about.diagram.text` |  | Message text | मैसेज टेक्स्ट |  |
| 161 | `about.diagram.screenshot` |  | Screenshot | स्क्रीनशॉट |  |
| 162 | `about.diagram.ocr` |  | OCR (EasyOCR) | OCR (EasyOCR) |  |
| 163 | `about.diagram.mask` |  | Clean + mask links, ⏎ phone numbers, OTPs | सफ़ाई + लिंक, फ़ोन नंबर, ⏎ OTP छिपाना |  |
| 164 | `about.diagram.classifier` |  | TF-IDF ⏎ classifier | TF-IDF ⏎ क्लासिफ़ायर |  |
| 165 | `about.diagram.url` |  | Link ⏎ analyzer | लिंक ⏎ जाँच |  |
| 166 | `about.diagram.rag` |  | Known-pattern ⏎ search (RAG) | पैटर्न की ⏎ खोज (RAG) |  |
| 167 | `about.diagram.rules` |  | Fixed verdict rules | तय निष्कर्ष नियम |  |
| 168 | `about.diagram.llm` |  | AI explainer (Groq / Gemini) ⏎ or template fallback | AI व्याख्या (Groq / Gemini) ⏎ या टेम्पलेट |  |
| 169 | `about.diagram.output` |  | Verdict, risk, warning signs, advice | निष्कर्ष, जोखिम, चेतावनी संकेत, सलाह |  |
| 170 | `about.steps.1` |  | Screenshots are read on the server with EasyOCR (English + Hindi). Timestamps and app buttons are removed. | स्क्रीनशॉट सर्वर पर EasyOCR (अंग्रेज़ी + हिंदी) से पढ़े जाते हैं। समय और ऐप के बटन हटा दिए जाते हैं। |  |
| 171 | `about.steps.2` |  | Links, phone numbers and one-time codes are masked, so the AI never sees them. | लिंक, फ़ोन नंबर और वन-टाइम कोड छिपा दिए जाते हैं, ताकि AI उन्हें कभी न देखे। |  |
| 172 | `about.steps.3` |  | A TF-IDF + Linear SVM classifier scores the text. A rule-based analyzer checks each link (look-alike brand domains, risky endings like .tk, a known-phishing list). | एक TF-IDF + Linear SVM क्लासिफ़ायर टेक्स्ट को स्कोर करता है। नियमों पर आधारित जाँच हर लिंक को परखती है (ब्रांड जैसे दिखने वाले डोमेन, .tk जैसे जोखिम भरे अंत, फ़िशिंग की जानी-पहचानी सूची)। |  |
| 173 | `about.steps.4` |  | A search over 25 documented patterns (14 scam types and 11 genuine message types) finds the closest match, using multilingual embeddings. | 25 दर्ज पैटर्न (14 तरह के स्कैम और 11 तरह के असली मैसेज) में से सबसे मिलता-जुलता पैटर्न बहुभाषी एम्बेडिंग से खोजा जाता है। |  |
| 174 | `about.steps.5` |  | Fixed, documented rules turn the classifier and link results into the verdict and risk level. The AI cannot change them. | तय और दर्ज नियम क्लासिफ़ायर और लिंक जाँच के नतीजों से निष्कर्ष और जोखिम का स्तर तय करते हैं। AI इन्हें बदल नहीं सकता। |  |
| 175 | `about.steps.6` |  | An AI model (Groq, with Gemini as backup) writes the explanation and advice in the message's language. If both are unavailable, templates are used. | एक AI मॉडल (Groq, बैकअप में Gemini) मैसेज की भाषा में व्याख्या और सलाह लिखता है। दोनों उपलब्ध न हों तो टेम्पलेट इस्तेमाल होते हैं। |  |
| 176 | `about.resultsHeading` |  | Honest results | ईमानदार नतीजे |  |
| 177 | `about.resultsIntro` |  | Every number below is copied from the project's results.md, with the section it came from. The test set is real messages only ({rows} messages, {scamShare} scams). | नीचे का हर आँकड़ा प्रोजेक्ट की results.md से लिया गया है, साथ में उसका सेक्शन भी दिया गया है। टेस्ट सेट में केवल असली मैसेज हैं ({rows} मैसेज, {scamShare} स्कैम)। |  |
| 178 | `about.sourcePrefix` |  | Source: results.md › | स्रोत: results.md › |  |
| 179 | `about.tableCaption` |  | Text classifiers on the real test set | असली टेस्ट सेट पर टेक्स्ट क्लासिफ़ायर |  |
| 180 | `about.colSystem` |  | System | सिस्टम |  |
| 181 | `about.colThreshold` |  | Decision threshold | फ़ैसले की सीमा (threshold) |  |
| 182 | `about.colF1` |  | F1 | F1 |  |
| 183 | `about.colAuc` |  | ROC-AUC | ROC-AUC |  |
| 184 | `about.colUnseen` |  | ROC-AUC on a source never seen in training | ट्रेनिंग में कभी न देखे गए स्रोत पर ROC-AUC |  |
| 185 | `about.colPromo` |  | Genuine promotions flagged | असली प्रमोशन जो गलती से पकड़े गए |  |
| 186 | `about.deployedTag` |  | deployed | इस्तेमाल में |  |
| 187 | `about.operatingPoint.f1Tuned` |  | F1-tuned | F1 के लिए तय |  |
| 188 | `about.operatingPoint.recallFirst` |  | Recall-first | रिकॉल पहले |  |
| 189 | `about.statsHeading` | **NEW** | At a glance | एक नज़र में |  |
| 190 | `about.stats.f1` | **NEW** | F1 of the deployed model on real test messages | असली टेस्ट मैसेज पर इस्तेमाल में मौजूद मॉडल का F1 |  |
| 191 | `about.stats.promo` | **NEW** | Genuine promotions and service messages wrongly flagged | असली प्रमोशनल और सर्विस मैसेज जो गलती से पकड़े गए |  |
| 192 | `about.stats.unseen` | **NEW** | ROC-AUC on a message source never seen in training: close to chance | ट्रेनिंग में कभी न देखे गए मैसेज स्रोत पर ROC-AUC: लगभग अंदाज़े जितना |  |
| 193 | `about.stats.rag` | **NEW** | Right pattern in the top 3, for real messages | असली मैसेज में सही पैटर्न टॉप 3 में |  |
| 194 | `about.tablesHeading` | **NEW** | Full results | पूरे नतीजे |  |
| 195 | `about.findingsHeading` |  | What the numbers mean | इन आँकड़ों का मतलब |  |
| 196 | `about.findings.transformer` |  | The fine-tuned transformer (DistilBERT) did not beat the simple TF-IDF model. With the same threshold rule, its F1 was higher by only +0.0004 (95% interval -0.0085 to +0.0097), which is within noise. The small, fast TF-IDF + Linear SVM model is the one deployed. | फ़ाइन-ट्यून किया गया ट्रांसफ़ॉर्मर (DistilBERT) साधारण TF-IDF मॉडल से बेहतर नहीं निकला। एक ही threshold नियम के साथ उसका F1 केवल +0.0004 ज़्यादा था (95% अंतराल -0.0085 से +0.0097), जो संयोग की सीमा के भीतर है। इसलिए छोटा और तेज़ TF-IDF + Linear SVM मॉडल इस्तेमाल में है। |  |
| 197 | `about.findings.unseen` |  | All models generalise poorly to a kind of message they never saw. Trained without the phishing-email source and tested on it, ROC-AUC falls to 0.5977 (TF-IDF + Linear SVM) and 0.5487 (DistilBERT), close to chance. | सभी मॉडल ऐसे मैसेज पर कमज़ोर हैं जो उन्होंने कभी नहीं देखे। फ़िशिंग ईमेल वाले स्रोत के बिना ट्रेन करके उसी पर जाँचने से ROC-AUC गिरकर 0.5977 (TF-IDF + Linear SVM) और 0.5487 (DistilBERT) रह जाता है, यानी लगभग अंदाज़े जितना। |  |
| 198 | `about.findings.promotions` |  | The deployed model flags 19% of the 153 genuine promotional and service messages in the test set. Expect false alarms on real marketing messages. | इस्तेमाल में मौजूद मॉडल टेस्ट सेट के 153 असली प्रमोशनल और सर्विस मैसेज में से 19% को गलती से पकड़ता है। असली मार्केटिंग मैसेज पर गलत चेतावनी की उम्मीद रखें। |  |
| 199 | `about.findings.rag` |  | Known-pattern search puts the right pattern in its top 3 for 89% of the evaluation messages, but for only 76% of the 17 real ones. The rest were written by the project author, so the overall number is optimistic. | जाने-पहचाने पैटर्न की खोज मूल्यांकन के 89% मैसेज में सही पैटर्न को टॉप 3 में रखती है, पर 17 असली मैसेज में केवल 76% में। बाकी मैसेज प्रोजेक्ट के लेखक ने लिखे थे, इसलिए कुल आँकड़ा ज़्यादा अच्छा दिखता है। |  |
| 200 | `about.findings.ocr` |  | Screenshot reading was measured only on 5 generated screenshots: character error rate 0.000 to 0.031. The method was tuned on these same images, so these numbers are optimistic. | स्क्रीनशॉट पढ़ना केवल 5 बनाए गए स्क्रीनशॉट पर मापा गया: कैरेक्टर एरर रेट 0.000 से 0.031। तरीका इन्हीं इमेज पर सुधारा गया था, इसलिए ये आँकड़े ज़्यादा अच्छे दिखते हैं। |  |
| 201 | `about.findings.realScreenshots` |  | The check on real phone screenshots has not been run yet. | असली फ़ोन स्क्रीनशॉट की जाँच अभी नहीं हुई है। |  |
| 202 | `about.findings.noIndianSet` |  | There is no real Indian test set yet, so accuracy on real Hindi and Hinglish messages has not been measured. | अभी असली भारतीय मैसेज का कोई टेस्ट सेट नहीं है, इसलिए असली हिंदी और हिंग्लिश मैसेज पर सटीकता नहीं मापी गई है। |  |
| 203 | `about.ragHeading` |  | Known-pattern search | जाने-पहचाने पैटर्न की खोज |  |
| 204 | `about.ragCaption` |  | Right pattern found, by evaluation split | सही पैटर्न मिला, मूल्यांकन के हिस्से के अनुसार |  |
| 205 | `about.colSplit` |  | Messages | मैसेज |  |
| 206 | `about.colN` |  | Count | संख्या |  |
| 207 | `about.colTop1` |  | Top 1 | टॉप 1 |  |
| 208 | `about.colTop3` |  | Top 3 | टॉप 3 |  |
| 209 | `about.ragSplit.overall` |  | All | सभी |  |
| 210 | `about.ragSplit.written` |  | Written by the author | लेखक के लिखे हुए |  |
| 211 | `about.ragSplit.real` |  | Real messages | असली मैसेज |  |
| 212 | `about.ocrHeading` |  | Screenshot reading (generated images only) | स्क्रीनशॉट पढ़ना (केवल बनाई गई इमेज) |  |
| 213 | `about.ocrCaption` |  | OCR on generated screenshots: synthetic and optimistic | बनाए गए स्क्रीनशॉट पर OCR: सिंथेटिक और ज़्यादा अच्छे दिखने वाले आँकड़े |  |
| 214 | `about.ocrNote` |  | Warm OCR took {min} to {max} seconds per image on the development machine, which is not the deployment hardware. | डेवलपमेंट मशीन पर (जो डिप्लॉयमेंट हार्डवेयर नहीं है) OCR में हर इमेज पर {min} से {max} सेकंड लगे। |  |
| 215 | `about.colSample` |  | Sample | सैंपल |  |
| 216 | `about.colCer` |  | Character error rate | कैरेक्टर एरर रेट |  |
| 217 | `about.colKeywords` |  | Keywords found | मिले हुए कीवर्ड |  |
| 218 | `about.colVerdict` |  | Verdict / risk | निष्कर्ष / जोखिम |  |
| 219 | `about.privacyHeading` |  | Privacy | गोपनीयता |  |
| 220 | `about.privacy.1` |  | Your text is sent to this project's API to be checked. | आपका टेक्स्ट जाँच के लिए इस प्रोजेक्ट के API पर भेजा जाता है। |  |
| 221 | `about.privacy.2` |  | Links, phone numbers and one-time codes are masked before any text goes to Groq or Google Gemini. These are third-party AI services with their own data policies. | कोई भी टेक्स्ट Groq या Google Gemini को भेजने से पहले लिंक, फ़ोन नंबर और वन-टाइम कोड छिपा दिए जाते हैं। ये बाहरी AI सेवाएँ हैं जिनकी अपनी डेटा नीतियाँ हैं। |  |
| 222 | `about.privacy.3` |  | Screenshots are read on our server. Only the masked text taken from them goes to an AI model, never the image. | स्क्रीनशॉट हमारे सर्वर पर पढ़े जाते हैं। AI मॉडल को केवल उनसे निकला छिपाया हुआ टेक्स्ट जाता है, इमेज कभी नहीं। |  |
| 223 | `about.privacy.4` |  | Nothing is logged or stored except feedback: if you answer "Was this correct?", only the result ID and your answer are saved (plus the result labels), never any text. | फ़ीडबैक के अलावा कुछ भी लॉग या सेव नहीं होता: अगर आप "क्या यह सही था?" का जवाब देते हैं, तो केवल नतीजे की ID और आपका जवाब (साथ में नतीजे के लेबल) सेव होते हैं, कोई टेक्स्ट कभी नहीं। |  |
| 224 | `about.privacy.5` |  | This website contains no keys or passwords and talks only to the project's own API. | इस वेबसाइट में कोई की या पासवर्ड नहीं है और यह केवल प्रोजेक्ट के अपने API से बात करती है। |  |
| 225 | `about.limitsHeading` |  | Limitations | सीमाएँ |  |
| 226 | `about.limits.1` |  | This is an automated check and it can be wrong in both directions. When in doubt, contact the organisation through its official app or number. | यह एक स्वचालित जाँच है और दोनों तरफ़ गलत हो सकती है। शक हो तो संस्था से उसके आधिकारिक ऐप या नंबर पर संपर्क करें। |  |
| 227 | `about.limits.2` |  | Tamil, Telugu, Bengali and Marathi messages mixed with English are not specially handled; explanations for them are in English. | अंग्रेज़ी के साथ मिली तमिल, तेलुगु, बांग्ला और मराठी के मैसेज को खास तौर पर संभाला नहीं जाता; उनकी व्याख्या अंग्रेज़ी में होती है। |  |
| 228 | `about.limits.3` |  | The link check never opens links; it only looks at how they are written. | लिंक जाँच लिंक कभी नहीं खोलती; वह केवल यह देखती है कि लिंक कैसे लिखा गया है। |  |
| 229 | `about.limits.4` |  | Until the backend is hosted, this website always runs in demo mode: it shows recorded real results for the samples only. | बैकएंड होस्ट होने तक यह वेबसाइट हमेशा डेमो मोड में चलती है: यह केवल सैंपल के रिकॉर्ड किए गए असली नतीजे दिखाती है। |  |
| 230 | `about.sourceHeading` |  | Source and details | सोर्स और विवरण |  |
| 231 | `about.sourceText` |  | The full evaluation, data sources and design decisions are in the project README and results.md. | पूरा मूल्यांकन, डेटा के स्रोत और डिज़ाइन के फ़ैसले प्रोजेक्ट की README और results.md में हैं। |  |
| 232 | `about.repoLink` |  | Project README on GitHub | GitHub पर प्रोजेक्ट की README |  |

## Footer

| # | Key | Status | English | Current Hindi | Your correction |
|---:|---|---|---|---|---|
| 233 | `footer.disclaimer` |  | Automated assessment - it can be wrong. Never share OTPs, PINs or passwords. | स्वचालित जाँच - यह गलत हो सकती है। OTP, PIN या पासवर्ड कभी साझा न करें। |  |
| 234 | `footer.project` |  | Portfolio project | पोर्टफ़ोलियो प्रोजेक्ट |  |
