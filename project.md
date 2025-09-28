# mastodon toot to blog post maker (“blog launcher”)

## input:
Mastodon URL of TAIL of toot thread
e.g. https://mastodon.social/@kaflurbaleen/115260626867209630


## alternate input:

Several different thread URLs that can be combined into a longer post

## output:

A markdown file containing all of the toots in the thread, organized into sections, with all images mentioned downloaded and links to them rewritten to show the local files. Assume the cwd will be served with a local web server.

## other examples:
1. emmy ceramics mold firing https://mastodon.social/@kaflurbaleen/113976812513907295 (should have 3 posts)
  1.5 later post in above thread of emmy mug https://mastodon.social/@kaflurbaleen/113976822706915052
2. emmy mug: https://mastodon.social/@kaflurbaleen/114004280173557894 (1 post)
3. plaster cast emmy https://mastodon.social/@kaflurbaleen/113240851757198355
4. 3d printing emmy https://mastodon.social/@kaflurbaleen/112963772568819837 
5. dragon wings https://mastodon.social/@kaflurbaleen/113303876487936684 (only partly - i took more photos much later and didnt toot them)
6. valentines: https://mastodon.social/@kaflurbaleen/111915106631644826 (already in blog form: https://blog.superfiretruck.com/post/valentines/) 

# TODO

- [x] make output folder named by date of oldest post in thred
- [x] get alt text of images and use that in the blog post text
- [x] allow multiple post urls to be entered and get all ancestors and images and then concatenate into one blog post
- [ ] make format of blog post a bit better - not showing individual posts but making it hugo format and making it like a draft blog post i can go in and edit and flesh out, but it could still have links to the original toots somewhere in it