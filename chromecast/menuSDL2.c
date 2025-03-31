#include <SDL2/SDL.h>
#include <SDL2/SDL_ttf.h>
#include "SDL_image.h"
#include <dirent.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>

#define MOVIES_DIR "/Volumes/EASYROMS/movies"
#define MAX_FILES 256
#define MAX_FILENAME 512
#define MAX_PATH 1024

SDL_Rect file_rects[MAX_FILES];
char files[MAX_FILES][MAX_FILENAME];
int file_count = 0;
char current_path[MAX_PATH];

int compare_base_names(const void *a, const void *b) {
    const char *s1 = (const char *)a;
    const char *s2 = (const char *)b;
    char name1[MAX_FILENAME], name2[MAX_FILENAME];

    if (s1[0] == '[') {
        strncpy(name1, s1 + 1, MAX_FILENAME - 1);
        char *end = strrchr(name1, ']');
        if (end) *end = '\0';
    } else {
        strncpy(name1, s1, MAX_FILENAME - 1);
        char *dot = strrchr(name1, '.');
        if (dot) *dot = '\0';
    }

    if (s2[0] == '[') {
        strncpy(name2, s2 + 1, MAX_FILENAME - 1);
        char *end = strrchr(name2, ']');
        if (end) *end = '\0';
    } else {
        strncpy(name2, s2, MAX_FILENAME - 1);
        char *dot = strrchr(name2, '.');
        if (dot) *dot = '\0';
    }

    name1[MAX_FILENAME - 1] = '\0';
    name2[MAX_FILENAME - 1] = '\0';
    return strcasecmp(name1, name2);
}

void load_movie_files() {
    file_count = 0;
    DIR *d;
    struct dirent *dir;

    char folder_list[MAX_FILES][MAX_FILENAME];
    char file_list[MAX_FILES][MAX_FILENAME];
    int folder_count = 0;
    int media_count = 0;

    d = opendir(current_path);
    if (d) {
        if (strcmp(current_path, MOVIES_DIR) != 0) {
            snprintf(files[file_count++], MAX_FILENAME, ".. (Back)");
        }

        while ((dir = readdir(d)) != NULL) {
            const char *name = dir->d_name;

            if (strcmp(name, ".") == 0 || strcmp(name, "..") == 0 || strcmp(name, "Program") == 0 || name[0] == '.') continue;
            if (dir->d_type == DT_DIR) {
                snprintf(folder_list[folder_count++], MAX_FILENAME, "[%s]", name);
            } else if (dir->d_type == DT_REG) {
                char *dot = strrchr(name, '.');
                if (dot && strcmp(dot, ".c") != 0) {
                    snprintf(file_list[media_count++], MAX_FILENAME, "%s", name);
                }
            }
        }
        closedir(d);

        qsort(folder_list, folder_count, MAX_FILENAME, compare_base_names);
        qsort(file_list, media_count, MAX_FILENAME, compare_base_names);

        for (int i = 0; i < folder_count && file_count < MAX_FILES; i++) {
            strncpy(files[file_count++], folder_list[i], MAX_FILENAME);
        }
        for (int i = 0; i < media_count && file_count < MAX_FILES; i++) {
            strncpy(files[file_count++], file_list[i], MAX_FILENAME);
        }
    }
}

void change_directory(const char *entry) {
    if (strcmp(entry, ".. (Back)") == 0) {
        char *last_slash = strrchr(current_path, '/');
        if (last_slash && last_slash != current_path) {
            *last_slash = '\0';
        } else {
            strcpy(current_path, MOVIES_DIR);
        }
    } else {
        const char *dirname = entry + 1;
        char folder[MAX_FILENAME];
        strncpy(folder, dirname, strlen(dirname) - 1);
        folder[strlen(dirname) - 1] = '\0';
        strncat(current_path, "/", MAX_PATH - strlen(current_path) - 1);
        strncat(current_path, folder, MAX_PATH - strlen(current_path) - 1);
    }
}

void cast_movie(const char *filename) {
    char fullpath[1024];
    snprintf(fullpath, sizeof(fullpath), "%s/%s", current_path, filename);

    if (fork() == 0) {
        execl("/Users/duncangoddard/.local/bin/catt", "catt", "stop", (char *)NULL);
        _exit(1);
    } else {
        wait(NULL);
    }

    if (fork() == 0) {
        execl("/Users/duncangoddard/.local/bin/catt", "catt", "cast", fullpath, (char *)NULL);
        _exit(1);
    }
}

int main() {
    SDL_Init(SDL_INIT_VIDEO);
    TTF_Init();
    IMG_Init(IMG_INIT_JPG);  // <-- NEW

    strcpy(current_path, MOVIES_DIR);
    load_movie_files();

    SDL_Window *win = SDL_CreateWindow("TreenySendy - Cast movies", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, 800, 600, 0);
    SDL_Renderer *ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED);
    TTF_Font *font = TTF_OpenFont("font.ttf", 28);

    SDL_Surface *bgSurf = IMG_Load("love.jpeg");  // <-- NEW
    SDL_Texture *bgTex = NULL;
    if (bgSurf) {
        bgTex = SDL_CreateTextureFromSurface(ren, bgSurf);
        SDL_FreeSurface(bgSurf);
    }

    int highlight = 0, casting = 0, running = 1;
    SDL_Event e;

    SDL_ShowCursor(SDL_ENABLE); // optional, ensures visible cursor

    while (running) {
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_MOUSEBUTTONDOWN && e.button.button == SDL_BUTTON_LEFT && !casting) {
                int mx = e.button.x, my = e.button.y;
                for (int i = 0; i < file_count; i++) {
                    if (SDL_PointInRect(&(SDL_Point){mx, my}, &file_rects[i])) {
                        highlight = i;
                        if (strncmp(files[i], "[", 1) == 0 || strcmp(files[i], ".. (Back)") == 0) {
                            change_directory(files[i]);
                            load_movie_files();
                            highlight = 0;
                        } else {
                            cast_movie(files[i]);
                            casting = 1;
                        }
                        break;
                    }
                }
            }

            if (e.type == SDL_KEYDOWN) {
                switch (e.key.keysym.sym) {
                    case SDLK_ESCAPE:
                        if (casting) {
                            system("/Users/duncangoddard/.local/bin/catt stop");
                            casting = 0;
                        } else {
                            running = 0;
                        }
                        break;
                    case SDLK_UP:
                        if (!casting && highlight > 0) highlight--;
                        break;
                    case SDLK_DOWN:
                        if (!casting && highlight < file_count - 1) highlight++;
                        break;
                    case SDLK_RETURN:
                        if (!casting) {
                            if (strncmp(files[highlight], "[", 1) == 0 || strcmp(files[highlight], ".. (Back)") == 0) {
                                change_directory(files[highlight]);
                                load_movie_files();
                                highlight = 0;
                            } else {
                                cast_movie(files[highlight]);
                                casting = 1;
                            }
                        }
                        break;
                }
            }
        }

        // Render background or fallback color
        if (bgTex) {
            SDL_RenderCopy(ren, bgTex, NULL, NULL);
            SDL_SetRenderDrawBlendMode(ren, SDL_BLENDMODE_BLEND);
            SDL_SetRenderDrawColor(ren, 0, 0, 0, 80);
            SDL_Rect overlay = {0, 0, 800, 600};
            SDL_RenderFillRect(ren, &overlay);
        } else {
            SDL_SetRenderDrawColor(ren, 15, 15, 15, 255);
            SDL_RenderClear(ren);
        }

        // Header love message
        SDL_Color loveColor = {255, 105, 180};
        const char *loveText = "This is for my love whom I love.";
        SDL_Surface *loveSurf = TTF_RenderText_Solid(font, loveText, loveColor);
        SDL_Texture *loveTex = SDL_CreateTextureFromSurface(ren, loveSurf);
        SDL_Rect loveDest = {50, 10, loveSurf->w, loveSurf->h};
        SDL_RenderCopy(ren, loveTex, NULL, &loveDest);
        SDL_FreeSurface(loveSurf);
        SDL_DestroyTexture(loveTex);

        for (int i = 0; i < file_count; i++) {
            SDL_Color color = (i == highlight) ? (SDL_Color){255, 200, 50} : (SDL_Color){255, 255, 255};
            SDL_Surface *surf = TTF_RenderText_Solid(font, files[i], color);
            SDL_Texture *tex = SDL_CreateTextureFromSurface(ren, surf);
            SDL_Rect dest = {50, 60 + i * 30, surf->w, surf->h};
            file_rects[i] = dest;
            SDL_RenderCopy(ren, tex, NULL, &dest);
            SDL_FreeSurface(surf);
            SDL_DestroyTexture(tex);
        }

        if (casting) {
            static int frame = 0;
            static Uint32 last_heart_time = 0;
            Uint32 now = SDL_GetTicks();

            if (now - last_heart_time > 300) {
                frame = (frame + 1) % 5;
                last_heart_time = now;
            }

            const char *hearts[] = {":)", "I", "<3", "LOVE", "TREENIE"};
            SDL_Color pink = {255, 100, 150};
            SDL_Surface *heartSurf = TTF_RenderText_Solid(font, hearts[frame], pink);
            SDL_Texture *heartTex = SDL_CreateTextureFromSurface(ren, heartSurf);
            SDL_Rect heartDest = {600, 100, heartSurf->w, heartSurf->h};
            SDL_RenderCopy(ren, heartTex, NULL, &heartDest);
            SDL_FreeSurface(heartSurf);
            SDL_DestroyTexture(heartTex);
        }

        // Footer
        SDL_Color footerColor = {180, 180, 180};
        const char *footerText = casting
            ? "ESC Stop"
            : "UP DOWN Navigate    ENTER Cast    ESC Quit";
        SDL_Surface *footerSurf = TTF_RenderText_Solid(font, footerText, footerColor);
        SDL_Texture *footerTex = SDL_CreateTextureFromSurface(ren, footerSurf);
        SDL_Rect footerDest = {50, 560, footerSurf->w, footerSurf->h};
        SDL_RenderCopy(ren, footerTex, NULL, &footerDest);
        SDL_FreeSurface(footerSurf);
        SDL_DestroyTexture(footerTex);

        SDL_RenderPresent(ren);
        SDL_Delay(16);
    }

    // Cleanup
    if (bgTex) SDL_DestroyTexture(bgTex);
    TTF_CloseFont(font);
    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    TTF_Quit();
    IMG_Quit();  // <-- NEW
    SDL_Quit();
    return 0;
}
