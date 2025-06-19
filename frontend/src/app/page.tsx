"use client"

import React, { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Loader2 } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import LoadingDots from '@/components/LoadingDots'
import { ChevronDown, ChevronUp, Search } from 'lucide-react';
import YouTube from 'react-youtube';

const API_URL_PROD: String = 'https://ta-python-v1.onrender.com/api';
const API_URL_DEV: String = 'http://localhost:8080/api';
const API_URL: String = API_URL_DEV;

// Define the Step type
type Step = {
  name: string;
  status: 'upcoming' | 'current' | 'completed';
};

interface TranscriptEntry {
  id: number;
  text: string;
  start: number;
  duration: number;
}

interface SummaryEntry {
  text: string;
  ref_id: number;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  similarQuestions?: string[];
  isExpanded?: boolean;
}

interface ChatSource {
  text: string;
  start: number;
  duration: number;
}

interface TopChunk {
  content: string;
  metadata: {
    start: number;
    duration: number;
    chunk_id: number;
  };
}

const formatTimestamp = (seconds: number): string => {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainingSeconds = Math.floor(seconds % 60)
  
  if (hours > 0) {
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`
  }
  return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`
}

function Page() {
  const [videoUrl, setVideoUrl] = useState<string>("")
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([])
  const [summary, setSummary] = useState<SummaryEntry[]>([])
  const [notes, setNotes] = useState<string>("")
  const [transcriptLoading, setTranscriptLoading] = useState<boolean>(false)
  const [summaryLoading, setSummaryLoading] = useState<boolean>(false)
  const [notesLoading, setNotesLoading] = useState<boolean>(false)
  const [progress, setProgress] = useState<number>(0)
  const [status, setStatus] = useState<string>("")
  const [error, setError] = useState<string>("")
  const [summarySteps, setSummarySteps] = useState<Step[]>([
    { name: 'Prepare', status: 'upcoming' },
    { name: 'Chunk', status: 'upcoming' },
    { name: 'Summarize', status: 'upcoming' },
    { name: 'Finalize', status: 'upcoming' }
  ]);
  const [notesSteps, setNotesSteps] = useState<Step[]>([
    { name: 'Prepare', status: 'upcoming' },
    { name: 'Generate', status: 'upcoming' },
    { name: 'Finalize', status: 'upcoming' }
  ]);
  const transcriptRef = useRef<HTMLDivElement>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatSources, setChatSources] = useState<ChatSource[]>([])
  const chatContainerRef = useRef<HTMLDivElement>(null)
  const [isAiResponding, setIsAiResponding] = useState(false)
  const [highlightedEntryId, setHighlightedEntryId] = useState<number | null>(null);
  const [videoId, setVideoId] = useState<string>("")
  const [playerRef, setPlayerRef] = useState<any>(null)
  const [videoDuration, setVideoDuration] = useState<number>(0);

  useEffect(() => {
    if (chatContainerRef.current) {
      const scrollArea = chatContainerRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (scrollArea) {
        scrollArea.scrollTop = scrollArea.scrollHeight;
      }
    }
  }, [chatMessages]);

  const extractVideoId = (url: string): string => {
    const regex = /(?:youtube\.com\/(?:[^\/\n\s]+\/\s*(?:\w*\/)*|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
    const match = url.match(regex);
    return match ? match[1] : "";
  }

  const handleTimestampClick = (startTime: number, duration: number) => {
    if (playerRef) {
      playerRef.seekTo(startTime);
      playerRef.playVideo();
    }
  };

  const handleTranscriptSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setTranscriptLoading(true)
    setError("")
    setTranscript([])
    setSummary([])
    setProgress(0)
    setStatus("")
    
    const extractedVideoId = extractVideoId(videoUrl);
    setVideoId(extractedVideoId);

    const eventSource = new EventSource(API_URL + `/transcript?video_url=${encodeURIComponent(videoUrl)}`)

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      console.log('Transcript data:', data)
      if (data.error) {
        setError(data.error)
        setTranscriptLoading(false)
        eventSource.close()
      } else if (data.progress) {
        console.log('Transcript progress:', data)
        setProgress(data.progress)
        setStatus(data.status)
        if (data.progress === 100) {
          setTranscript(data.transcript)
          setTranscriptLoading(false)
          eventSource.close()
        }
      }
    }

    eventSource.onerror = (err) => {
      console.error("EventSource failed:", err);
      setError("An error occurred while processing the video. Please try again later or check the server logs for more information.")
      setTranscriptLoading(false)
      eventSource.close()
    }
  }

  const formatTime = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const remainingSeconds = Math.floor(seconds % 60)
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`
  }

  const handleSummarySubmit = async () => {
    setSummaryLoading(true)
    setError("")
    setSummary([])
    setProgress(0)
    setStatus("")

    try {
      const response = await fetch(API_URL + '/summary', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ transcript }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error("Failed to get response reader")
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const messages = new TextDecoder().decode(value).split('\n\n')
        for (const message of messages) {
          if (message.startsWith('data: ')) {
            const data = JSON.parse(message.slice(6))
            if (data.error) {
              setError(data.error)
              setSummaryLoading(false)
            } else if (data.progress) {
              setProgress(data.progress)
              setStatus(data.status)
              updateSummarySteps(data.status)
              if (data.progress === 100) {
                setSummary(data.summary)
                setSummaryLoading(false)
                if (data.summary && data.summary[0] && typeof data.summary[0].text === 'string') {
                  setChatMessages(prev => [...prev, { 
                    role: 'assistant', 
                    content: data.summary[0].text 
                  }])
                }
              }
            }
          }
        }
      }
    } catch (error) {
      setError("An error occurred while summarizing the transcript")
      setSummaryLoading(false)
    }
  }


 
  const handleMakeNotes = async () => {
    setNotesLoading(true)
    setError("")
    setNotes("")
    setProgress(0)
    setStatus("")

    try {
      const response = await fetch(API_URL + '/notes', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ transcript }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error("Failed to get response reader")
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const messages = new TextDecoder().decode(value).split('\n\n')
        for (const message of messages) {
          if (message.startsWith('data: ')) {
            const data = JSON.parse(message.slice(6))
            if (data.error) {
              setError(data.error)
              setNotesLoading(false)
            } else if (data.progress) {
              setProgress(data.progress)
              setStatus(data.status)
              updateNotesSteps(data.status)
              if (data.progress === 100 && data.notes) {
                const cleanedNotes = typeof data.notes === 'string' 
                  ? data.notes.replace(/^##\s*/gm, '')
                  : data.notes;
                
                setNotes(cleanedNotes)
                setNotesLoading(false)
                
                setChatMessages(prev => [...prev, { 
                  role: 'assistant', 
                  content: cleanedNotes
                }])
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('Error in handleMakeNotes:', error)
      setError("An error occurred while generating notes")
      setNotesLoading(false)
    }
  }

  const updateSummarySteps = (status: string) => {
    setSummarySteps(steps => {
      const newSteps = [...steps];
      if (status.includes("Preparing")) {
        newSteps[0].status = 'current';
      } else if (status.includes("chunk")) {
        newSteps[0].status = 'completed';
        newSteps[1].status = 'current';
        newSteps[2].status = 'current';
      } else if (status.includes("Finalizing")) {
        newSteps[0].status = 'completed';
        newSteps[1].status = 'completed';
        newSteps[2].status = 'completed';
        newSteps[3].status = 'current';
      }
      return newSteps;
    });
  }

  const updateNotesSteps = (status: string) => {
    setNotesSteps(steps => {
      const newSteps = [...steps];
      if (status.includes("Preparing")) {
        newSteps[0].status = 'current';
      } else if (status.includes("Finalizing")) {
        newSteps[0].status = 'completed';
        newSteps[1].status = 'completed';
        newSteps[2].status = 'current';
      } else {
        newSteps[0].status = 'completed';
        newSteps[1].status = 'current';
      }
      return newSteps;
    });
  }

  const scrollToNearestTranscriptEntry = (refNumber: number) => {
    if (transcriptRef.current) {
      const transcriptEntries = Array.from(transcriptRef.current.querySelectorAll('.transcript-entry'));
      let closestEntry = transcriptEntries[0];
      let smallestDifference = Infinity;

      for (const entry of transcriptEntries) {
        const entryId = parseInt((entry as HTMLElement).dataset.id || '0');
        const difference = Math.abs(entryId - (refNumber - 1));
        if (difference < smallestDifference) {
          smallestDifference = difference;
          closestEntry = entry;
        }
      }

      if (closestEntry) {
        closestEntry.scrollIntoView({ behavior: 'smooth', block: 'center' });
        const entryId = parseInt((closestEntry as HTMLElement).dataset.id || '0');
        setHighlightedEntryId(entryId);
        
        // Play video from the timestamp of the highlighted chunk
        if (transcript[entryId]) {
          const nextChunkStart = transcript[entryId + 1]?.start;
          handleTimestampClick(transcript[entryId].start, nextChunkStart);
        }
      }
    }
  };

  const renderChatMessage = (content: string) => {
    return (
      <div className="markdown-content space-y-4 text-black">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({node, ...props}) => <h1 className="text-2xl font-bold mt-8 mb-4 text-black block" {...props} />,
            h2: ({node, ...props}) => <h2 className="text-xl font-bold mt-6 mb-3 text-black block" {...props} />,
            h3: ({node, ...props}) => <h3 className="text-lg font-semibold mt-4 mb-2 text-black block" {...props} />,
            p: ({node, children, ...props}) => {
              const text = Array.isArray(children) ? children.join('') : children?.toString() || '';
              return <p className="text-base text-black mb-4" {...props}>{processTextWithReferences(text)}</p>;
            },
            ul: ({node, ...props}) => <ul className="list-disc pl-5 mb-4 text-black text-base" {...props} />,
            ol: ({node, ...props}) => <ol className="list-decimal pl-5 mb-4 text-black text-base" {...props} />,
            li: ({node, children, ...props}) => {
              const childrenArray = React.Children.toArray(children);
              return (
                <li className="mb-2 text-base text-black flex items-start" {...props}>
                  <span className="mr-2">•</span>
                  <span className="flex-1">
                    {childrenArray.map((child, index) => 
                      typeof child === 'string' ? processTextWithReferences(child) : child
                    )}
                  </span>
                </li>
              );
            },
            strong: ({node, ...props}) => <strong className="text-base font-bold text-black" {...props} />,
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    )
  }

  const processTextWithReferences = (text: string) => {
    // Match both timestamp format [MM:SS] and reference numbers [1]
    const parts = text.split(/(\[\d+:\d+(?::\d+)?\]|\[\d+\])/);
    return parts.map((part, index) => {
      // Match reference number [1]
      const refMatch = part.match(/\[(\d+)\]/);
      if (refMatch) {
        const refNumber = parseInt(refMatch[1]);
        return (
          <button
            key={index}
            className="inline-flex items-center justify-center font-bold text-white bg-[#3180DB] bg-opacity-60 rounded-full w-[26px] h-[26px] text-xs cursor-pointer ml-1 hover:bg-opacity-100"
            onClick={() => scrollToNearestTranscriptEntry(refNumber)}
          >
            {refNumber}
          </button>
        );
      }
      return part;
    });
  };

  const handleChatSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMessage: ChatMessage = { role: 'user', content: chatInput };
    setChatMessages(prev => [...prev, userMessage]);
    setIsAiResponding(true);
    const currentInput = chatInput;
    setChatInput('');

    try {
      const response = await fetch(API_URL + '/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: currentInput, transcript: transcript }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('Chat response:', data);
      // Log the top chunks used for processing the answer
      // console.log('Top chunks used for answer:', data.top_chunks.map((chunk: TopChunk, index: number) => ({
      //   chunk_number: index + 1,
      //   timestamp: formatTime(chunk.metadata.start),
      //   content: chunk.content,
      //   metadata: chunk.metadata
      // })));
      
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: data.answer, 
        isExpanded: true
      };
      setChatMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error in chat:', error);
      setChatMessages(prev => [...prev, {
        role: 'assistant',
        content: 'I apologize, but I encountered an error while processing your request.'
      }]);
    } finally {
      setIsAiResponding(false);
    }
  };

  const clearHighlight = () => {
    setHighlightedEntryId(null);
  };

  const handleSimilarQuestionClick = async (question: string) => {
    const userMessage: ChatMessage = { role: 'user', content: question };
    setChatMessages(prev => [...prev, userMessage]);
    setIsAiResponding(true);

    try {
      const response = await fetch(API_URL + '/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: question }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: data.answer,
        similarQuestions: data.similar_questions,
        isExpanded: true
      };
      setChatMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error in chat:', error);
      setChatMessages(prev => [...prev, {
        role: 'assistant',
        content: 'I apologize, but I encountered an error while processing your request.'
      }]);
    } finally {
      setIsAiResponding(false);
    }
  };

  const opts = {
    width: '100%',
    height: '200',
    playerVars: {
      autoplay: 0,
      rel: 0,
      showinfo: 0,
      controls: 1,
      modestbranding: 1
    },
  };

  const onReady = (event: any) => {
    if (event?.target) {
      setPlayerRef(event.target);
      setVideoDuration(event.target.getDuration());
    }
  };

  // Add this useEffect for cleanup
  useEffect(() => {
    return () => {
      if (playerRef) {
        playerRef.destroy();
      }
    };
  }, [playerRef]);

  // Update the existing useEffect for chat scrolling
  useEffect(() => {
    // Add a small delay to ensure content is rendered
    const scrollTimeout = setTimeout(() => {
      if (chatContainerRef.current) {
        const scrollArea = chatContainerRef.current.querySelector('[data-radix-scroll-area-viewport]');
        if (scrollArea) {
          scrollArea.scrollTop = scrollArea.scrollHeight;
        }
      }
    }, 100); // 100ms delay

    return () => clearTimeout(scrollTimeout);
  }, [chatMessages, isAiResponding]); // Add isAiResponding to dependencies

  return (
    <div className="flex h-screen">
      <div className="w-[40%] flex flex-col bg-white overflow-hidden">
        <div className="p-6 pb-4 pr-12">
          <div className="flex items-center mb-4">
            <h2 className="text-xl font-bold text-gray-800 mr-4">TRANSCRIPT</h2>
            <form onSubmit={handleTranscriptSubmit} className="flex-grow">
              <div className="flex items-center bg-white rounded-[15px] overflow-hidden border border-gray-300">
                <Input
                  type="text"
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                  placeholder="Enter YouTube Video URL"
                  className="flex-grow h-10 text-sm focus:ring-0 focus:outline-none border-none rounded-none text-black" 
                />
                <Button 
                  type="submit" 
                  disabled={transcriptLoading}
                  className="h-10 px-4 text-sm focus:ring-0 focus:outline-none bg-[#3180DB] hover:bg-[#2670CB] text-white rounded-none" 
                >
                  {transcriptLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  {transcriptLoading ? 'Processing...' : 'Transcribe'}
                </Button>
              </div>
            </form>
          </div>
        </div>
        
        {videoId && (
          <div className="px-8 mb-4">
            <div className="max-w-[500px] mx-auto">
              <div className="relative w-full" style={{ paddingTop: '56.25%' }}>
                <div className="absolute top-0 left-0 w-full h-full rounded-xl overflow-hidden">
                  <YouTube
                    videoId={videoId}
                    opts={opts}
                    onReady={onReady}
                    className="w-full h-full"
                    iframeClassName="w-full h-full"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        <ScrollArea className="flex-grow px-6 custom-scrollbar" ref={transcriptRef}>
          <div className="pr-2 pl-2">
            <AnimatePresence>
              {transcript.map((entry) => (
                <motion.div
                  key={entry.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.3 }}
                >
                  <Card 
                    className={`mb-5 transcript-entry hover:bg-gray-50 transition-colors duration-200 rounded-[15px] border border-gray-200 shadow-[0_0_8px_rgba(0,0,0,0.05)] ${
                      entry.id === highlightedEntryId ? 'bg-blue-50' : 'bg-white'
                    }`} 
                    data-id={entry.id}
                  >
                    <CardContent className="p-4 flex items-start">
                      <div className="flex items-center space-x-2 mr-4 flex-shrink-0">
                        <button 
                          className="px-2 py-1 bg-[#3180DB] bg-opacity-60 text-white text-xs rounded-[4px] hover:bg-opacity-100 transition-opacity"
                          onClick={() => handleTimestampClick(entry.start, entry.duration)}
                        >
                          {formatTimestamp(entry.start)}
                        </button>
                      </div>
                      <span className="text-sm text-black flex-grow pr-2">
                        {entry.text}
                      </span>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </ScrollArea>
      </div>

      <div className="w-[60%] flex flex-col h-screen bg-neutral-100">
        <div className="p-8 flex flex-col h-full">
          <h2 className="text-2xl font-bold mb-4 text-black text-center">CHATBOT</h2>
          
          <ScrollArea 
            className="flex-grow mb-6 pr-4" 
            ref={chatContainerRef}
            scrollHideDelay={0}
          >
            <div className="space-y-4">
              <AnimatePresence>
                {chatMessages.map((message, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                    className={`${message.role === 'user' ? 'text-right' : 'text-left'}`}
                  >
                    {message.role === 'user' ? (
                      <span className="inline-block p-3 bg-blue-100 rounded-[15px] text-black text-base whitespace-normal">
                        {message.content}
                      </span>
                    ) : (
                      <div className="w-full">
                        {/* Search and Similar Questions Header */}
                        {message.similarQuestions && message.similarQuestions.length > 0 && (
                          <div className="bg-white rounded-t-[15px] border-t border-l border-r border-gray-200 overflow-hidden">
                            <div 
                              className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-50"
                              onClick={() => {
                                setChatMessages(prev => prev.map((msg, i) => 
                                  i === index ? { ...msg, isExpanded: !msg.isExpanded } : msg
                                ));
                              }}
                            >
                              <div className="flex items-center space-x-2">
                                <Search className="w-4 h-4 text-gray-500" />
                                <span className="text-sm text-gray-700">Searched</span>
                              </div>
                              <div className="flex items-center space-x-2">
                                <span className="text-sm text-gray-700">Collapse Steps</span>
                                {message.isExpanded ? (
                                  <ChevronUp className="w-4 h-4 text-gray-500" />
                                ) : (
                                  <ChevronDown className="w-4 h-4 text-gray-500" />
                                )}
                              </div>
                            </div>

                            {/* Similar Questions Section */}
                            {message.isExpanded && (
                              <div className="border-t border-gray-200">
                                <div className="p-4">
                                  <div className="flex items-center space-x-2 mb-3">
                                    <div className="w-4 h-4 bg-blue-500 rounded-full flex items-center justify-center">
                                      <span className="text-white text-xs">✓</span>
                                    </div>
                                    <span className="font-medium text-sm">Searched across transcript</span>
                                  </div>
                                  
                                  <div className="pl-6">
                                    <span className="text-sm text-gray-500 mb-2 block">Searched</span>
                                    <div className="space-y-2">
                                      {Array.isArray(message.similarQuestions) ? 
                                        message.similarQuestions.map((question, idx) => (
                                          <div
                                            key={idx}
                                            className="inline-block mr-2 mb-2 px-3 py-1.5 bg-gray-100 rounded-full text-sm text-gray-700"
                                          >
                                            {typeof question === 'string' ? question : JSON.stringify(question)}
                                          </div>
                                        ))
                                        : null
                                      }
                                    </div>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                        
                        {/* AI Response */}
                        <div className={`p-5 border border-gray-200 bg-white ${
                          message.similarQuestions && message.similarQuestions.length > 0 
                            ? 'rounded-b-[15px] border-t-0'
                            : 'rounded-[15px]'
                        } text-black text-base whitespace-normal`}>
                          {renderChatMessage(message.content)}
                        </div>
                      </div>
                    )}
                  </motion.div>
                ))}
                {isAiResponding && (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                    className="text-left"
                  >
                    <span className="inline-block p-3 rounded-[15px] bg-gray-50 text-black text-sm">
                      <LoadingDots />
                    </span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </ScrollArea>

          {/* Bottom section with buttons and input */}
          <div className="space-y-4">
            {/* Summarize and Make Notes buttons */}
            <div className="flex space-x-3">
              <Button 
                onClick={handleSummarySubmit} 
                disabled={summaryLoading || notesLoading}
                className="h-10 px-4 text-sm focus:ring-0 focus:outline-none bg-[#3180DB] hover:bg-[#2670CB] text-white rounded-[8px]"
              >
                {summaryLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {summaryLoading ? 'Summarizing...' : 'Summarize'}
              </Button>
              <Button 
                onClick={handleMakeNotes} 
                disabled={summaryLoading || notesLoading}
                className="h-10 px-4 text-sm focus:ring-0 focus:outline-none bg-[#3180DB] hover:bg-[#2670CB] text-white rounded-[8px] font-bold"
              >
                {notesLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {notesLoading ? 'Generating Study Notes...' : 'Make Study Notes'}
              </Button>
            </div>

            {/* Chat input form */}
            <form onSubmit={handleChatSubmit} className="flex">
              <div className="flex flex-grow items-center bg-white rounded-[15px] overflow-hidden border border-gray-300">
                <Input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="Ask a question about the transcript..."
                  className="flex-grow h-12 text-md focus:ring-0 focus:outline-none border-none rounded-none pl-4 text-black"
                />
                <Button 
                  type="submit"
                  className="h-12 px-6 text-md focus:ring-0 focus:outline-none bg-[#3180DB] hover:bg-[#2670CB] text-white rounded-none"
                >
                  Send
                </Button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Page
